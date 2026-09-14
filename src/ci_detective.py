#!/usr/bin/env python3
from __future__ import annotations
import json,os,re,subprocess,sys
from dataclasses import dataclass,field
from typing import Any

COMMAND_TIMEOUT=30

@dataclass
class Diagnosis:
    category:str
    summary:str
    evidence:list[str]=field(default_factory=list)
    confidence:str="low"
    failing_tests:list[str]=field(default_factory=list)
    traceback_files:list[str]=field(default_factory=list)
    error_lines:list[str]=field(default_factory=list)
    history:list[str]=field(default_factory=list)
    root_cause:str=""
    implicated_symbol:str=""

def run_command(command:list[str],**kwargs:Any)->subprocess.CompletedProcess[str]:
    kwargs.setdefault("timeout",COMMAND_TIMEOUT)
    kwargs.setdefault("env",os.environ.copy())
    return subprocess.run(command,**kwargs)

PATTERNS=[
("typeerror","TYPE_ERROR","A TypeError was detected; inspect the failing call and recent signature changes.","high"),
("assertionerror","ASSERTION_FAILURE","An assertion failed; inspect the expected and actual values.","high"),
("modulenotfounderror","IMPORT_FAILURE","A Python module import failed; inspect dependencies and import paths.","high"),
("cannot find module","IMPORT_FAILURE","A Node.js module import failed; inspect dependencies and package configuration.","high"),
("npm err!","NPM_FAILURE","npm reported an installation or script failure.","medium"),
("command not found","COMMAND_FAILURE","A required executable was not available in the runner environment.","high"),
("permission denied","PERMISSION_FAILURE","A command or file operation was denied by the runner environment.","high"),
("out of memory","RESOURCE_FAILURE","The job appears to have exhausted available memory.","medium"),
("timed out","TIMEOUT","The job appears to have exceeded a timeout.","medium")]

def clean_logs(text:str)->str:return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]","",text or "")

def extract_failing_tests(text:str)->list[str]:
    found=[]
    for p in [r"(?:FAILED|ERROR)\s+([\w./\\-]+::[\w./:\-]+)",r"(?:^|\s)FAIL(?!ED):?\s+([\w./\\-]+::[\w./:\-]+)"]:
        for m in re.finditer(p,clean_logs(text),re.I|re.M):
            v=m.group(1).strip().rstrip(".,")
            if v and v not in found:found.append(v)
    return found[:10]

def extract_error_lines(text:str)->list[str]:
    out=[]
    for line in clean_logs(text).splitlines():
        s=line.strip()
        if re.search(r"\b(?:TypeError|AssertionError|ModuleNotFoundError|ImportError|ReferenceError|SyntaxError|Error):",s) or s.lower().startswith(("npm err!","error:","fatal:")):
            if s:out.append(s[:500])
    return list(dict.fromkeys(out))[:8]

def extract_traceback_files(text:str)->list[str]:
    out=[]
    for p in [r'File ["\']([^"\']+\.(?:py|js|jsx|ts|tsx))["\'], line \d+',r'(?:at|in) ([^\s()]+\.(?:js|jsx|ts|tsx|py))(?::\d+)?']:
        for m in re.finditer(p,clean_logs(text)):
            v=m.group(1).replace("\\","/")
            if v not in out:out.append(v)
    return out[:10]

def infer_root_cause(text:str,category:str)->tuple[str,str,str]:
    if category=="TYPE_ERROR":
        m=re.search(r"([\w.]+)\(\)\s+missing\s+(\d+)\s+required positional argument[s]?:\s*['\"]([^'\"]+)['\"]",text,re.I)
        if m:return(f"The call to {m.group(1)} is missing required argument '{m.group(3)}'. The failure is consistent with a caller/signature mismatch.",m.group(1),"high")
        m=re.search(r"'([^']+)' object is not callable",text,re.I)
        if m:return(f"A value of type '{m.group(1)}' was called as a function, indicating an invalid callable assumption.","","high")
    if category=="ASSERTION_FAILURE":
        m=re.search(r"AssertionError:\s*(.+)",text,re.I)
        if m:return(f"The assertion failed because {m.group(1).strip()[:300]}","","high")
    if category=="IMPORT_FAILURE":
        m=re.search(r"No module named\s+['\"]([^'\"]+)['\"]",text,re.I) or re.search(r"Cannot find module\s+['\"]([^'\"]+)['\"]",text,re.I)
        if m:return(f"The runtime cannot resolve dependency/module '{m.group(1)}'.",m.group(1),"high")
    return("The available evidence identifies the failure class, but not a unique root cause.","","low")

def classify_failure(log_text:str)->Diagnosis:
    text=clean_logs(log_text); tests=extract_failing_tests(text); errors=extract_error_lines(text); files=extract_traceback_files(text)
    for needle,cat,summary,conf in PATTERNS:
        if needle in text.lower():
            evidence=(["Failing test: "+tests[0]] if tests else [])+errors[:4]
            if not evidence:evidence=[x.strip()[:500] for x in text.splitlines() if needle in x.lower()][:1]
            root,symbol,rc=infer_root_cause(text,cat)
            return Diagnosis(cat,root if rc=="high" else summary,list(dict.fromkeys(evidence)),"high" if rc=="high" else conf,tests,files,errors,[],root,symbol)
    if re.search(r"(?:^|\s)(?:FAILED|FAILURES|failed tests?|test suites? failed)\b",text,re.I):
        root,symbol,rc=infer_root_cause(text,"TEST_FAILURE")
        return Diagnosis("TEST_FAILURE",root,(["Failing test: "+tests[0]] if tests else [])+errors[:4],"high" if rc=="high" else "medium",tests,files,errors,[],root,symbol)
    return Diagnosis("UNKNOWN","The failure could not be classified by the current deterministic rules.",errors[:4],"low",tests,files,errors)

def gh_api(path:str,method:str="GET",payload:dict[str,Any]|None=None)->Any:
    if not os.environ.get("GH_TOKEN"):raise RuntimeError("GH_TOKEN is required")
    cmd=["gh","api",path]
    if method!="GET":cmd += ["--method",method]
    if payload is not None:cmd += ["--input","-"]
    r=run_command(cmd,input=json.dumps(payload) if payload is not None else None,check=True,capture_output=True,text=True)
    return json.loads(r.stdout) if r.stdout.strip() else {}

def github_comment_api(path:str,method:str="GET",payload:dict[str,Any]|None=None)->Any:
    token=os.environ.get("GH_TOKEN")
    if not token:raise RuntimeError("GH_TOKEN is required")
    cmd=["curl","-fsSL","-X",method,"-H",f"Authorization: Bearer {token}","-H","Accept: application/vnd.github+json","-H","X-GitHub-Api-Version: 2022-11-28"]
    if payload is not None:cmd += ["-H","Content-Type: application/json","--data-binary",json.dumps(payload,separators=(",",":"),ensure_ascii=False)]
    cmd.append("https://api.github.com/"+path.lstrip("/"))
    r=run_command(cmd,check=True,capture_output=True,text=True)
    return json.loads(r.stdout) if r.stdout.strip() else {}

def git_command(*args:str)->str:return run_command(["git",*args],check=True,capture_output=True,text=True).stdout

def _matching(changed:list[str],implicated:list[str])->list[str]:return[p for p in implicated if any(p==c or p.endswith("/"+c) or c.endswith("/"+p) for c in changed)]

def analyze_git_history(log_text:str)->list[str]:
    try:
        head=git_command("rev-parse","HEAD").strip(); parent=git_command("rev-parse","HEAD^").strip(); changed=[x.strip().replace("\\","/") for x in git_command("diff","--name-only",parent,head).splitlines() if x.strip()]; implicated=extract_traceback_files(log_text); matching=_matching(changed,implicated)
    except(subprocess.CalledProcessError,subprocess.TimeoutExpired,FileNotFoundError):return[]
    e=[f"Failure traceback references {p}, which changed in HEAD." for p in matching[:3]]
    if changed and implicated and not matching:e.append("The failure has a source traceback, but none of its files changed in HEAD.")
    if changed:e.append("HEAD changed: "+", ".join(changed[:10]))
    try:subject=git_command("log","-1","--format=%s",head).strip()
    except(subprocess.CalledProcessError,subprocess.TimeoutExpired):subject=""
    if subject:e.append(f"Current commit {head[:7]}: {subject}")
    if matching:e.append(f"Likely regression candidate: current commit {head[:7]} changed an implicated source file.")
    return e

def fetch_all_commit_files(repo:str,sha:str)->list[dict[str,Any]]:
    first=gh_api(f"repos/{repo}/commits/{sha}?per_page=100")
    if not isinstance(first,dict):return[]
    files=list(first.get("files",[]) or[])
    if len(files)<100:return files
    cmd=["gh","api","--paginate","--slurp",f"repos/{repo}/commits/{sha}?per_page=100"]
    r=run_command(cmd,check=True,capture_output=True,text=True)
    pages=json.loads(r.stdout) if r.stdout.strip() else[]
    all_files=[]
    for page in pages if isinstance(pages,list) else[]:
        if isinstance(page,dict):all_files.extend(page.get("files",[]) or[])
    return all_files or files

def analyze_remote_commit(repo:str,sha:str,implicated:list[str])->list[str]:
    if not repo or not sha or not implicated:return[]
    try:
        commit=gh_api(f"repos/{repo}/commits/{sha}")
        changed_files=fetch_all_commit_files(repo,sha)
    except(subprocess.CalledProcessError,subprocess.TimeoutExpired,json.JSONDecodeError,TypeError,ValueError,OSError) as exc:
        return [f"Remote commit analysis unavailable: {type(exc).__name__}."]
    if not isinstance(commit,dict):return["Remote commit analysis unavailable: invalid API response."]
    changed=[f.get("filename","") for f in changed_files if isinstance(f,dict) and f.get("filename")]; matching=_matching(changed,implicated); e=[f"Failure traceback references {p}, which changed in the failing commit." for p in matching[:3]]
    if changed:e.append("Failing commit changed: "+", ".join(changed[:10]))
    message=commit.get("commit",{}).get("message","").splitlines()[0]
    if message:e.append(f"Failing commit {sha[:7]}: {message}")
    if matching:e.append(f"Likely regression candidate: failing commit {sha[:7]} changed an implicated source file.")
    return e

def fetch_job_logs(repo:str,run_id:str,job_id:int)->str:
    token=os.environ.get("GH_TOKEN")
    if not token:raise RuntimeError("GH_TOKEN is required")
    url=f"https://api.github.com/repos/{repo}/actions/jobs/{job_id}/logs"; r=run_command(["curl","-fsSL","-H",f"Authorization: Bearer {token}","-H","Accept: application/vnd.github+json",url],capture_output=True,text=True,timeout=60)
    if r.returncode==0 and r.stdout.strip():return r.stdout
    try:
        jobs=gh_api(f"repos/{repo}/actions/runs/{run_id}/jobs?per_page=100"); job=next((x for x in jobs.get("jobs",[]) if int(x.get("id",-1))==job_id),None)
        if not job:return""
        r=run_command(["gh","run","view",run_id,"--repo",repo,"--job",str(job_id),"--log","--color","never"],capture_output=True,text=True,timeout=60); return r.stdout if r.returncode==0 else""
    except(subprocess.CalledProcessError,subprocess.TimeoutExpired,TypeError,ValueError):return""

def fetch_all_pr_comments(repo:str,pr_number:int)->list[dict[str,Any]]:
    first=github_comment_api(f"repos/{repo}/issues/{pr_number}/comments?per_page=100")
    if not isinstance(first,list):return[]
    if len(first)<100:return first
    cmd=["gh","api","--paginate","--slurp",f"repos/{repo}/issues/{pr_number}/comments?per_page=100"]
    r=run_command(cmd,check=True,capture_output=True,text=True)
    pages=json.loads(r.stdout) if r.stdout.strip() else[]
    all_comments=[]
    for page in pages if isinstance(pages,list) else[]:
        if isinstance(page,list):all_comments.extend(page)
    return all_comments or first

def render_markdown_report(job_name:str,d:Diagnosis)->str:
    lines=["## CI Detective — Failure Diagnosis","",f"**Job:** `{job_name}`  ",f"**Category:** `{d.category}`  ",f"**Confidence:** **{d.confidence.upper()}**","","### Diagnosis",d.summary]
    if d.root_cause and d.root_cause!=d.summary:lines += ["","### Root Cause",d.root_cause]
    if d.implicated_symbol:lines += ["","### Implicated Symbol",f"`{d.implicated_symbol}`"]
    if d.failing_tests:lines += ["","### Failing Tests"]+[f"- `{x}`" for x in d.failing_tests[:5]]
    if d.traceback_files:lines += ["","### Traceback Files"]+[f"- `{x}`" for x in d.traceback_files[:5]]
    if d.evidence:lines += ["","### Evidence"]+[f"- {x}" for x in d.evidence[:6]]
    if d.history:lines += ["","### Git History"]+[f"- {x}" for x in d.history[:6]]
    if any("Likely regression candidate" in x for x in d.history+d.evidence):lines += ["","### Assessment","**Likely regression detected:** No. The changed-file match is only a correlation signal and is not sufficient to establish causation."]
    elif d.category=="UNKNOWN":lines += ["","### Assessment","No deterministic root cause was established. Treat this result as a triage signal, not a definitive diagnosis."]
    return "\n".join(lines+["","---","Generated by CI Detective — deterministic analysis; no external AI required",""])

def render_multi_job_report(ds:list[tuple[str,Diagnosis]])->str:
    lines=["## CI Detective — Failure Diagnosis","",f"**Failed jobs:** **{len(ds)}**"]
    for i,(name,d) in enumerate(ds,1):
        lines += ["",f"### Failed Job {i}: `{name}`","",f"**Category:** `{d.category}`  ",f"**Confidence:** **{d.confidence.upper()}**","","#### Diagnosis",d.summary]
        if d.root_cause and d.root_cause!=d.summary:lines += ["","#### Root Cause",d.root_cause]
        if d.implicated_symbol:lines += ["","#### Implicated Symbol",f"`{d.implicated_symbol}`"]
        if d.failing_tests:lines += ["","#### Failing Tests"]+[f"- `{x}`" for x in d.failing_tests[:5]]
        if d.traceback_files:lines += ["","#### Traceback Files"]+[f"- `{x}`" for x in d.traceback_files[:5]]
        if d.evidence:lines += ["","#### Evidence"]+[f"- {x}" for x in d.evidence[:6]]
        if d.history:lines += ["","#### Git History"]+[f"- {x}" for x in d.history[:6]]
        if any("Likely regression candidate" in x for x in d.history+d.evidence):lines += ["","#### Assessment","**Likely regression detected:** No. The changed-file match is only a correlation signal and is not sufficient to establish causation."]
        elif d.category=="UNKNOWN":lines += ["","#### Assessment","No deterministic root cause was established. Treat this result as a triage signal, not a definitive diagnosis."]
    return "\n".join(lines+["","---","Generated by CI Detective — deterministic analysis; no external AI required",""])

def build_diagnosis_payload(ds:list[tuple[str,Diagnosis]])->dict[str,Any]:
    return {"schema_version":"1.0","failed_jobs":[{"job":name,"category":d.category,"confidence":d.confidence,"summary":d.summary,"root_cause":d.root_cause,"implicated_symbol":d.implicated_symbol,"failing_tests":d.failing_tests,"traceback_files":d.traceback_files,"history":d.history} for name,d in ds]}

def write_step_summary(report:str)->None:
    p=os.environ.get("GITHUB_STEP_SUMMARY")
    if p:
        with open(p,"a",encoding="utf-8") as f:f.write(report)

def pull_request_number()->int|None:
    p=os.environ.get("GITHUB_EVENT_PATH")
    if not p:return None
    try:
        with open(p,encoding="utf-8") as f:e=json.load(f)
        n=e.get("pull_request",{}).get("number") or e.get("issue",{}).get("number"); return int(n) if n is not None else None
    except(OSError,json.JSONDecodeError,TypeError,ValueError):return None

def post_or_update_pr_comment(repo:str,pr_number:int,report:str)->str:
    marker="<!-- ci-detective -->"; body=marker+"\n"+report; comments=fetch_all_pr_comments(repo,pr_number)
    existing=next((c for c in comments if marker in c.get("body","") and c.get("user",{}).get("type")=="Bot"),None)
    if existing:github_comment_api(f"repos/{repo}/issues/comments/{existing['id']}","PATCH",{"body":body});return"updated"
    github_comment_api(f"repos/{repo}/issues/{pr_number}/comments","POST",{"body":body});return"created"

def main()->int:
    repo,run_id=os.environ.get("GITHUB_REPOSITORY"),os.environ.get("GITHUB_RUN_ID")
    if not repo or not run_id:print("CI Detective: GitHub Actions environment not detected.");return 0
    try:
        jobs=gh_api(f"repos/{repo}/actions/runs/{run_id}/jobs?per_page=100"); failed=[j for j in jobs.get("jobs",[]) if j.get("conclusion")=="failure"]
        if not failed:print("CI Detective: no failed jobs found.");return 0
        ds=[]; sha=os.environ.get("GITHUB_SHA","")
        for job in failed:
            logs=fetch_job_logs(repo,run_id,int(job["id"]))
            d=classify_failure(logs); d.history=analyze_git_history(logs) or analyze_remote_commit(repo,sha,d.traceback_files); ds.append((job.get("name","unknown job"),d))
        report=render_multi_job_report(ds);print(report);write_step_summary(report)
        if os.environ.get("INPUT_COMMENT_ON_PR","true").lower()=="true":
            n=pull_request_number()
            if n:
                try:print(f"CI Detective: PR comment {post_or_update_pr_comment(repo,n,report)}.")
                except Exception as exc:print(f"CI Detective warning: PR comment delivery failed: {exc}",file=sys.stderr)
            else:print("CI Detective: no pull request context; skipping PR comment.")
        p=os.environ.get("GITHUB_OUTPUT")
        if p:
            payload=build_diagnosis_payload(ds); primary=ds[0][1]
            with open(p,"a",encoding="utf-8") as f:
                f.write(f"diagnosis={json.dumps(payload,separators=(',',':'))}\nconfidence={primary.confidence}\nschema_version=1.0\n")
        return 0
    except Exception as exc:print(f"CI Detective error: {exc}",file=sys.stderr);return 1

if __name__=="__main__":sys.exit(main())