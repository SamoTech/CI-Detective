#!/usr/bin/env python3
"""CI Detective: deterministic, evidence-first GitHub Actions failure analysis."""
from __future__ import annotations
import json, os, re, subprocess, sys
from dataclasses import dataclass, field
from typing import Any

@dataclass
class Diagnosis:
    category: str
    summary: str
    evidence: list[str] = field(default_factory=list)
    confidence: str = "low"
    failing_tests: list[str] = field(default_factory=list)
    traceback_files: list[str] = field(default_factory=list)
    error_lines: list[str] = field(default_factory=list)
    history: list[str] = field(default_factory=list)
    root_cause: str = ""
    implicated_symbol: str = ""

PATTERNS = [
    ("typeerror", "TYPE_ERROR", "A TypeError was detected; inspect the failing call and recent signature changes.", "high"),
    ("assertionerror", "ASSERTION_FAILURE", "An assertion failed; inspect the expected and actual values.", "high"),
    ("modulenotfounderror", "IMPORT_FAILURE", "A Python module import failed; inspect dependencies and import paths.", "high"),
    ("cannot find module", "IMPORT_FAILURE", "A Node.js module import failed; inspect dependencies and package configuration.", "high"),
    ("npm err!", "NPM_FAILURE", "npm reported an installation or script failure.", "medium"),
    ("command not found", "COMMAND_FAILURE", "A required executable was not available in the runner environment.", "high"),
    ("permission denied", "PERMISSION_FAILURE", "A command or file operation was denied by the runner environment.", "high"),
    ("out of memory", "RESOURCE_FAILURE", "The job appears to have exhausted available memory.", "medium"),
    ("timed out", "TIMEOUT", "The job appears to have exceeded a timeout.", "medium"),
]

def clean_logs(text: str) -> str:
    return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text or "")

def extract_failing_tests(log_text: str) -> list[str]:
    found=[]
    for pattern in [r"(?:FAILED|ERROR)\s+([\w./\\-]+::[\w./:\-]+)", r"(?:^|\s)FAIL(?!ED):?\s+([\w./\\-]+::[\w./:\-]+)"]:
        for m in re.finditer(pattern, clean_logs(log_text), re.I|re.M):
            v=m.group(1).strip().rstrip(".,")
            if v and v not in found: found.append(v)
    return found[:10]

def extract_error_lines(log_text: str) -> list[str]:
    found=[]
    for line in clean_logs(log_text).splitlines():
        s=line.strip()
        if re.search(r"\b(?:TypeError|AssertionError|ModuleNotFoundError|ImportError|ReferenceError|SyntaxError|Error):",s) or s.lower().startswith(("npm err!","error:","fatal:")):
            if s: found.append(s[:500])
    return list(dict.fromkeys(found))[:8]

def extract_traceback_files(log_text: str) -> list[str]:
    found=[]
    for pattern in [r'File ["\']([^"\']+\.(?:py|js|jsx|ts|tsx))["\'], line \d+', r'(?:at|in) ([^\s()]+\.(?:js|jsx|ts|tsx|py))(?::\d+)?']:
        for m in re.finditer(pattern,clean_logs(log_text)):
            p=m.group(1).replace("\\","/")
            if p not in found: found.append(p)
    return found[:10]

def infer_root_cause(text: str, category: str) -> tuple[str,str,str]:
    if category == "TYPE_ERROR":
        m=re.search(r"([\w.]+)\(\)\s+missing\s+(\d+)\s+required positional argument[s]?:\s*['\"]([^'\"]+)['\"]",text,re.I)
        if m:
            symbol=m.group(1); arg=m.group(3)
            return (f"The call to {symbol} is missing required argument '{arg}'. The failure is consistent with a caller/signature mismatch.",symbol,"high")
        m=re.search(r"'([^']+)' object is not callable",text,re.I)
        if m: return (f"A value of type '{m.group(1)}' was called as a function, indicating an invalid callable assumption.","","high")
    if category == "ASSERTION_FAILURE":
        m=re.search(r"AssertionError:\s*(.+)",text,re.I)
        if m: return (f"The assertion failed because {m.group(1).strip()[:300]}","","high")
    if category == "IMPORT_FAILURE":
        m=re.search(r"No module named\s+['\"]([^'\"]+)['\"]",text,re.I)
        if not m:
            m=re.search(r"Cannot find module\s+['\"]([^'\"]+)['\"]",text,re.I)
        if m: return (f"The runtime cannot resolve dependency/module '{m.group(1)}'.",m.group(1),"high")
    return ("The available evidence identifies the failure class, but not a unique root cause.","","low")

def classify_failure(log_text: str) -> Diagnosis:
    text=clean_logs(log_text); lowered=text.lower()
    tests,errors,files=extract_failing_tests(text),extract_error_lines(text),extract_traceback_files(text)
    for needle,category,summary,confidence in PATTERNS:
        if needle in lowered:
            evidence=(["Failing test: "+tests[0]] if tests else [])+errors[:4]
            if not evidence:
                evidence=[line.strip()[:500] for line in text.splitlines() if needle in line.lower()][:1]
            root,symbol,root_conf=infer_root_cause(text,category)
            if root_conf=="high": summary=root; confidence="high"
            return Diagnosis(category,summary,list(dict.fromkeys(evidence)),confidence,tests,files,errors,[],root,symbol)
    if re.search(r"(?:^|\s)(?:FAILED|FAILURES|failed tests?|test suites? failed)\b",text,re.I):
        evidence=(["Failing test: "+tests[0]] if tests else [])+errors[:4]
        root,symbol,root_conf=infer_root_cause(text,"TEST_FAILURE")
        return Diagnosis("TEST_FAILURE",root,list(dict.fromkeys(evidence)),"high" if root_conf=="high" else "medium",tests,files,errors,[],root,symbol)
    return Diagnosis("UNKNOWN","The failure could not be classified by the current deterministic rules.",errors[:4],"low",tests,files,errors)

def gh_api(path: str, method: str = "GET", payload: dict[str,Any]|None = None) -> Any:
    if not os.environ.get("GH_TOKEN"): raise RuntimeError("GH_TOKEN is required")
    command=["gh","api",path]
    if method!="GET": command += ["--method",method]
    if payload is not None: command += ["--input","-"]
    result=subprocess.run(command,input=json.dumps(payload) if payload is not None else None,check=True,capture_output=True,text=True,env=os.environ.copy())
    return json.loads(result.stdout) if result.stdout.strip() else {}

def git_command(*args: str) -> str:
    return subprocess.run(["git",*args],check=True,capture_output=True,text=True,env=os.environ.copy()).stdout

def _matching(changed:list[str],implicated:list[str])->list[str]:
    return [p for p in implicated if any(p==c or p.endswith("/"+c) or c.endswith("/"+p) for c in changed)]

def analyze_git_history(log_text:str)->list[str]:
    try:
        head=git_command("rev-parse","HEAD").strip(); parent=git_command("rev-parse","HEAD^").strip()
        changed=[x.strip().replace("\\","/") for x in git_command("diff","--name-only",parent,head).splitlines() if x.strip()]
        implicated=extract_traceback_files(log_text); matching=_matching(changed,implicated)
    except (subprocess.CalledProcessError,FileNotFoundError): return []
    evidence=[f"Failure traceback references {p}, which changed in HEAD." for p in matching[:3]]
    if changed and implicated and not matching: evidence.append("The failure has a source traceback, but none of its files changed in HEAD.")
    if changed: evidence.append("HEAD changed: "+", ".join(changed[:10]))
    subject=git_command("log","-1","--format=%s",head).strip()
    if subject: evidence.append(f"Current commit {head[:7]}: {subject}")
    if matching: evidence.append(f"Likely regression candidate: current commit {head[:7]} changed an implicated source file.")
    return evidence

def analyze_remote_commit(repo:str,sha:str,implicated:list[str])->list[str]:
    if not repo or not sha or not implicated:return []
    try: commit=gh_api(f"repos/{repo}/commits/{sha}")
    except Exception:return []
    changed=[f.get("filename","") for f in commit.get("files",[]) if f.get("filename")]; matching=_matching(changed,implicated)
    evidence=[f"Failure traceback references {p}, which changed in the failing commit." for p in matching[:3]]
    if changed:evidence.append("Failing commit changed: "+", ".join(changed[:10]))
    message=commit.get("commit",{}).get("message","").splitlines()[0]
    if message:evidence.append(f"Failing commit {sha[:7]}: {message}")
    if matching:evidence.append(f"Likely regression candidate: failing commit {sha[:7]} changed an implicated source file.")
    return evidence

def fetch_job_logs(repo:str,run_id:str,job_id:int)->str:
    token=os.environ.get("GH_TOKEN")
    if not token: raise RuntimeError("GH_TOKEN is required")
    url=f"https://api.github.com/repos/{repo}/actions/jobs/{job_id}/logs"
    direct=subprocess.run(["curl","-fsSL","-H",f"Authorization: Bearer {token}","-H","Accept: application/vnd.github+json",url],capture_output=True,text=True,env=os.environ.copy())
    if direct.returncode==0 and direct.stdout.strip(): return direct.stdout
    fallback=subprocess.run(["gh","run","view",run_id,"--repo",repo,"--log-failed","--color","never"],capture_output=True,text=True,env=os.environ.copy())
    return fallback.stdout if fallback.returncode==0 else ""

def render_markdown_report(job_name:str,diagnosis:Diagnosis)->str:
    lines=["## CI Detective — Failure Diagnosis","",f"**Job:** `{job_name}`  ",f"**Category:** `{diagnosis.category}`  ",f"**Confidence:** **{diagnosis.confidence.upper()}**","","### Diagnosis",diagnosis.summary]
    if diagnosis.root_cause and diagnosis.root_cause!=diagnosis.summary: lines += ["", "### Root Cause", diagnosis.root_cause]
    if diagnosis.implicated_symbol: lines += ["", "### Implicated Symbol", f"`{diagnosis.implicated_symbol}`"]
    if diagnosis.failing_tests: lines += ["", "### Failing Tests"]+[f"- `{x}`" for x in diagnosis.failing_tests[:5]]
    if diagnosis.traceback_files: lines += ["", "### Traceback Files"]+[f"- `{x}`" for x in diagnosis.traceback_files[:5]]
    if diagnosis.evidence: lines += ["", "### Evidence"]+[f"- `{x}`" for x in diagnosis.evidence[:6]]
    if diagnosis.history: lines += ["", "### Git History"]+[f"- {x}" for x in diagnosis.history[:6]]
    combined=diagnosis.history+diagnosis.evidence
    if any("Likely regression candidate" in x for x in combined): lines += ["", "### Assessment","**Likely regression detected:** the failing commit modified a source file implicated by the failure traceback."]
    elif diagnosis.category=="UNKNOWN": lines += ["", "### Assessment","No deterministic root cause was established. Treat this result as a triage signal, not a definitive diagnosis."]
    lines += ["","---","Generated by CI Detective — deterministic analysis; no external AI required."]
    return "\n".join(lines)+"\n"

def write_step_summary(report:str)->None:
    path=os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path,"a",encoding="utf-8") as f:f.write(report)

def pull_request_number()->int|None:
    path=os.environ.get("GITHUB_EVENT_PATH")
    if not path:return None
    try:
        with open(path,encoding="utf-8") as f:event=json.load(f)
    except (OSError,json.JSONDecodeError):return None
    number=event.get("pull_request",{}).get("number") or event.get("issue",{}).get("number")
    try:return int(number) if number is not None else None
    except (TypeError,ValueError):return None

def post_or_update_pr_comment(repo:str,pr_number:int,report:str)->str:
    marker="<!-- ci-detective -->"; body=marker+"\n"+report
    comments=gh_api(f"repos/{repo}/issues/{pr_number}/comments?per_page=100")
    existing=next((c for c in comments if marker in c.get("body","") and c.get("user",{}).get("type")=="Bot"),None)
    if existing:
        gh_api(f"repos/{repo}/issues/comments/{existing['id']}","PATCH",{"body":body}); return "updated"
    gh_api(f"repos/{repo}/issues/{pr_number}/comments","POST",{"body":body}); return "created"

def main()->int:
    repo,run_id=os.environ.get("GITHUB_REPOSITORY"),os.environ.get("GITHUB_RUN_ID")
    if not repo or not run_id: print("CI Detective: GitHub Actions environment not detected."); return 0
    try:
        jobs=gh_api(f"repos/{repo}/actions/runs/{run_id}/jobs?per_page=100")
        failed=[j for j in jobs.get("jobs",[]) if j.get("conclusion")=="failure"]
        if not failed: print("CI Detective: no failed jobs found."); return 0
        diagnoses=[]; sha=os.environ.get("GITHUB_SHA","")
        for job in failed:
            logs=fetch_job_logs(repo,run_id,int(job["id"])); diagnosis=classify_failure(logs)
            diagnosis.history=analyze_git_history(logs) or analyze_remote_commit(repo,sha,diagnosis.traceback_files)
            diagnoses.append((job.get("name","unknown job"),diagnosis))
        name,diagnosis=diagnoses[0]; report=render_markdown_report(name,diagnosis); print(report); write_step_summary(report)
        if os.environ.get("INPUT_COMMENT_ON_PR","true").lower()=="true":
            pr_number=pull_request_number()
            if pr_number: print(f"CI Detective: PR comment {post_or_update_pr_comment(repo,pr_number,report)}.")
            else: print("CI Detective: no pull request context; skipping PR comment.")
        output_path=os.environ.get("GITHUB_OUTPUT")
        if output_path:
            payload={"category":diagnosis.category,"confidence":diagnosis.confidence,"summary":diagnosis.summary,"root_cause":diagnosis.root_cause,"implicated_symbol":diagnosis.implicated_symbol,"failing_tests":diagnosis.failing_tests,"traceback_files":diagnosis.traceback_files,"history":diagnosis.history}
            with open(output_path,"a",encoding="utf-8") as f:f.write(f"diagnosis={json.dumps(payload,separators=(',',':'))}\nconfidence={diagnosis.confidence}\n")
        return 0
    except Exception as exc: print(f"CI Detective error: {exc}",file=sys.stderr); return 1

if __name__=="__main__": raise SystemExit(main())
