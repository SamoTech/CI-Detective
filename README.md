# CI Detective

CI Detective analyzes failed GitHub Actions runs and produces evidence-based root-cause reports.

## Status

Early development. The first milestone is deterministic CI failure diagnosis with no paid AI dependency.

## What it does

CI Detective can classify common CI failures, extract source paths from Python and Node.js traces, correlate failures with files changed in the current commit, and publish a Markdown diagnosis to the GitHub Actions job summary.

When the workflow runs in a pull request and the token has issue-comment write permission, CI Detective can also publish the diagnosis as a PR conversation comment. A stable marker is used so subsequent runs update the existing CI Detective comment instead of creating duplicates.

## GitHub Actions usage

Run CI Detective in a separate job after the job that executes your tests:

```yaml
permissions:
  contents: read
  actions: read
  issues: write

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run tests
        run: python -m pytest -q

  diagnose:
    if: ${{ failure() }}
    needs: test
    runs-on: ubuntu-latest
    permissions:
      contents: read
      actions: read
      issues: write
    steps:
      - uses: actions/checkout@v4
      - uses: SamoTech/CI-Detective@main
        with:
          comment-on-pr: 'true'
```

The diagnostic job must be separate from the failed job because GitHub Actions job logs are available to the diagnostic job after the failed job has completed.

For fork-based pull requests, GitHub may restrict write permissions for the workflow token. In that case the diagnostic report remains available in the job summary, while the PR comment may be unavailable.

## Design principles

- Evidence first: reports are derived from logs and repository history.
- Deterministic core: no external AI service is required.
- GitHub-native: GitHub Actions and GitHub APIs are the primary runtime interfaces.
- Conservative attribution: the engine reports a regression candidate only when the traceback implicates a file changed by the current commit.
