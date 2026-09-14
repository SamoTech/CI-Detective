# CI Detective

CI Detective analyzes failed GitHub Actions runs and produces evidence-based root-cause reports.

## Current milestone

Deterministic CI failure diagnosis with no paid AI dependency. The engine extracts failing tests, error lines and traceback files, correlates them with Git history, and can publish the diagnosis to a Pull Request.

## Use in a workflow

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
      - uses: SamoTech/CI-Detective@main
        env:
          GH_TOKEN: ${{ github.token }}
```

When the workflow runs in Pull Request context, CI Detective adds or updates a single PR comment using a hidden marker, preventing duplicate comments. Set `comment-on-pr: 'false'` to disable PR comments. Fork pull requests may receive a read-only `GITHUB_TOKEN`, so PR comment delivery can be unavailable depending on repository and event permissions.

## Outputs

The action exposes `diagnosis`, `confidence`, and `schema_version` outputs. `diagnosis` is a versioned JSON payload containing all failed jobs; the current schema version is `1.0`.

## What it detects

- TypeError and common Python/JavaScript exceptions
- Assertion and test failures
- Import/module failures
- npm failures
- missing commands
- permission failures
- resource exhaustion
- timeouts
- likely regressions based on traceback files and changed files

Regression correlation is explicitly treated as evidence, not proof of causation.

## Design principles

1. Evidence before inference.
2. Deterministic analysis first.
3. No mandatory external AI service.
4. Never claim a root cause without supporting evidence.
5. GitHub Actions is the primary execution environment.
