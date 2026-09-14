# CI Detective

[![Tests](https://github.com/SamoTech/CI-Detective/actions/workflows/tests.yml/badge.svg)](https://github.com/SamoTech/CI-Detective/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

CI Detective is a GitHub Action that investigates failed GitHub Actions jobs and produces an evidence-based Markdown diagnosis plus machine-readable outputs.

It is designed for teams that want useful CI triage without sending every failure to a paid AI service.

## What you get

When a workflow fails, CI Detective can:

- identify the failed job or jobs
- isolate job-specific logs instead of mixing failures across jobs
- classify common failures such as `TypeError`, assertions, imports, npm errors, missing commands, permissions, resource exhaustion, and timeouts
- inspect traceback files, failing tests, changed files, commits, and relevant PR history
- assess possible regressions without treating a changed file as proof of causation
- publish a readable diagnosis to a Pull Request
- generate a customer-facing Markdown report
- upload the report as a GitHub Actions artifact when repository publishing is unavailable
- expose stable JSON outputs for automation
- optionally enhance the deterministic report with NVIDIA AI using live model discovery and same-API fallback

The deterministic analyzer remains authoritative. NVIDIA AI is advisory and can be disabled completely.

## Quick start

Add a diagnostic job after your normal test/build jobs:

```yaml
name: CI

on:
  push:
  pull_request:

permissions:
  contents: read
  actions: read

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pytest

  diagnose:
    if: ${{ failure() }}
    needs: test
    runs-on: ubuntu-latest
    permissions:
      contents: read
      actions: read
      issues: write
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Diagnose CI failure
        id: detective
        uses: SamoTech/CI-Detective@main
        env:
          GH_TOKEN: ${{ github.token }}
```

For production workflows, pin the Action to a reviewed release or commit SHA rather than following `main`.

## Pull Request comments

In Pull Request workflows, CI Detective can add or update one diagnosis comment. It uses an internal marker to avoid creating duplicate comments on repeated runs.

Disable comments with:

```yaml
with:
  comment-on-pr: 'false'
```

Forked Pull Requests may receive restricted token permissions. In those cases PR comment or repository-write operations may be unavailable; CI Detective is designed to continue with the report and deterministic analysis.

## Markdown reports

Every run attempts to produce a Markdown report.

By default the report is written to:

```text
.ci-detective/reports/ci-detective-report.md
```

The `report-destination` input controls delivery:

| Mode | Behavior |
| --- | --- |
| `auto` | Publish to the repository when `Contents: write` is available; otherwise keep the report in the workflow artifact/summary. |
| `repo` | Request repository publication. If GitHub does not allow the write, the action remains non-fatal and keeps the fallback report. |
| `none` | Do not publish the report to the repository. |

To publish directly into the customer repository, the calling job needs:

```yaml
permissions:
  contents: write
```

Then you can choose a repository path:

```yaml
with:
  report-destination: repo
  report-path: docs/ci-detective/report.md
```

The action also uploads a run-specific GitHub Actions artifact. If repository publishing is not possible, `report_url` points to the workflow run so the report remains accessible through the run artifact/summary.

Repository writes are intentionally optional. This prevents CI Detective from requiring write access just to diagnose a failure.

## Optional NVIDIA AI enhancement

NVIDIA AI is optional. The action first performs deterministic analysis. If `NVIDIA_API_KEY` is configured and `ai-analysis` is enabled, CI Detective:

1. queries NVIDIA's live model catalog
2. selects an appropriate currently available model from its supported free-model registry
3. sends the evidence context for advisory analysis
4. validates the response as structured JSON
5. automatically tries another currently available NVIDIA model if the selected model fails
6. keeps the deterministic diagnosis as the authoritative result if NVIDIA is unavailable

Enable it with:

```yaml
with:
  ai-analysis: 'true'
env:
  NVIDIA_API_KEY: ${{ secrets.NVIDIA_API_KEY }}
```

No NVIDIA key is required for the deterministic analyzer.

NVIDIA's free API access is intended for prototyping, testing, and evaluation and is subject to provider availability and rate limits. CI Detective does not attempt to bypass those limits.

## Action inputs

| Input | Default | Purpose |
| --- | --- | --- |
| `comment-on-pr` | `true` | Add/update the diagnosis PR comment when applicable. |
| `ai-analysis` | `true` | Run optional NVIDIA AI when `NVIDIA_API_KEY` is configured. |
| `report-destination` | `auto` | Choose `auto`, `repo`, or `none` for repository report persistence. |
| `report-path` | `.ci-detective/reports/ci-detective-report.md` | Repository-relative Markdown report path. |

## Action outputs

| Output | Description |
| --- | --- |
| `diagnosis` | Versioned JSON payload containing all failed jobs. |
| `confidence` | Primary deterministic diagnosis confidence. |
| `schema_version` | Current diagnosis schema version (`1.0`). |
| `ai_diagnosis` | Advisory NVIDIA AI JSON payload when available. |
| `ai_model` | NVIDIA model selected after live availability checks. |
| `ai_status` | NVIDIA AI status. |
| `report_path` | Generated report path. |
| `report_url` | Direct repository Markdown URL when published, otherwise workflow-run fallback. |
| `report_status` | Report persistence result (`repo` or `artifact`). |

Example:

```yaml
- name: Read diagnosis
  run: |
    echo "Confidence: ${{ steps.detective.outputs.confidence }}"
    echo "Report: ${{ steps.detective.outputs.report_url }}"
```

## Supported failure signals

CI Detective currently has deterministic handling for common signals including:

- Python and JavaScript `TypeError` and other common exceptions
- assertion and test failures
- import/module failures
- npm failures
- missing commands
- permission failures
- resource exhaustion
- timeouts
- likely regressions based on available Git and traceback evidence

The exact diagnosis depends on the evidence available in the failed workflow. When evidence is insufficient, CI Detective explicitly reports uncertainty instead of inventing a root cause.

## Architecture

```text
Failed GitHub Actions job(s)
          |
          v
  Deterministic analyzer
          |
          +----> isolated logs + tests + traceback + Git history
          |
          v
   Evidence-based report
          |
          +----> PR comment
          |
          +----> Markdown report
          |          |
          |          +----> repository (when permitted)
          |          +----> Actions artifact fallback
          |
          +----> optional NVIDIA AI advisory layer
                       |
                       +----> live model discovery
                       +----> capability-based selection
                       +----> same-API fallback
```

## Design principles

1. Evidence before inference.
2. Deterministic analysis first.
3. AI is optional, advisory, and replaceable.
4. Never claim causation from correlation alone.
5. Never invent files, tests, commits, causes, or fixes.
6. Keep CI diagnosis functional when external AI is unavailable.
7. Request the minimum GitHub permissions needed for each delivery mode.
8. Produce both human-readable and machine-readable results.

## Security and permissions

CI Detective operates inside the customer's GitHub Actions runner. It needs `actions: read` to inspect workflow/job information and `contents: read` for repository history and files. PR comments require `pull-requests: write` and/or `issues: write` as applicable.

Repository Markdown publication requires `contents: write`. Do not grant that permission unless you want CI Detective to commit reports into the repository.

For untrusted fork Pull Requests, prefer read-only permissions and rely on the workflow-run report fallback. Never expose an NVIDIA API key to untrusted workflow code.

See [SECURITY.md](SECURITY.md) for the project's security policy.

## Reliability model

A failed AI request does not make the CI diagnosis fail. The deterministic result is still emitted, and the report delivery path falls back when repository writes are unavailable.

Regression detection is deliberately conservative: a changed file may correlate with a failure, but CI Detective does not present that correlation as proof that the file caused the failure.

## Troubleshooting

### No PR comment appears

Check that the workflow has the required PR/issue write permission and that the event context provides a writable token. For forked PRs, use the workflow-run report instead.

### The Markdown report is not committed

Use `contents: write` on the diagnostic job and set `report-destination: repo`. Otherwise `auto` intentionally falls back to the Actions artifact/summary.

### NVIDIA AI is unavailable

Verify that `NVIDIA_API_KEY` is configured as a repository or organization secret. NVIDIA model availability and rate limits can change. Deterministic diagnosis does not require the key.

### The diagnosis says evidence is insufficient

That is an intentional safety behavior. Inspect the failed job's logs and rerun with full repository history (`fetch-depth: 0`) so Git-based evidence is available.

## Contributing

Bug reports, feature requests, documentation improvements, tests, and additional deterministic failure signatures are welcome.

See [CONTRIBUTING.md](CONTRIBUTING.md) before opening a change.

## License

CI Detective is released under the [MIT License](LICENSE).

## Project status

CI Detective is an actively developed GitHub Action. The deterministic analyzer is the core product; NVIDIA AI is an optional enhancement layer. Pin versions in production workflows and review release notes before upgrading.
