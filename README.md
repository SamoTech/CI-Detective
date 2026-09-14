# CI Detective

CI Detective analyzes failed GitHub Actions runs and produces evidence-based root-cause reports.

## Current milestone

Deterministic CI failure diagnosis with no paid AI dependency. The engine extracts failing tests, error lines and traceback files, correlates them with Git history, and can publish the diagnosis to a Pull Request.

## Use in a workflow

Keep read permissions at workflow scope and grant write permissions only to the detective job:

```yaml
permissions:
  contents: read
  actions: read

jobs:
  test:
    # your normal build/test job
    ...

  detect:
    if: ${{ failure() }}
    needs: test
    permissions:
      contents: read
      actions: read
      issues: write
      pull-requests: write
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: SamoTech/CI-Detective@main
        env:
          GH_TOKEN: ${{ github.token }}
```

When the workflow runs in Pull Request context, CI Detective adds or updates a single PR comment using a hidden marker, preventing duplicate comments. Set `comment-on-pr: 'false'` to disable PR comments.

For forked pull requests and other workflows where GitHub downgrades the available token permissions, PR comment creation or updates may be unavailable. Diagnosis in the job summary and JSON outputs should be treated as the primary result in those cases.

## Action outputs

The Action exposes a versioned `diagnosis` JSON payload containing every failed job, plus `confidence` and `schema_version` for the primary diagnosis. The current payload schema version is `1.0`.

## What it detects

- TypeError and common Python/JavaScript exceptions
- Assertion and test failures
- Import/module failures
- npm failures
- missing commands
- permission failures
- resource exhaustion
- timeouts
- regression signals based on traceback files and changed files; a changed-file match is correlation evidence, not proof of causation

## Design principles

1. Evidence before inference.
2. Deterministic analysis first.
3. No mandatory external AI service.
4. Never claim a root cause without supporting evidence.
5. GitHub Actions is the primary execution environment.
