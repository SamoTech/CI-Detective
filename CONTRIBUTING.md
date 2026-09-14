# Contributing to CI Detective

Thank you for contributing to CI Detective.

## Development

1. Create a focused branch from `main`.
2. Keep changes scoped to one feature, fix, or documentation improvement.
3. Add or update tests for behavioral changes.
4. Run the complete test suite with `python -m pytest -q`.
5. Verify GitHub Actions workflow changes with a representative workflow run.
6. Open a pull request with a concise description of the problem, implementation, and validation.

## Engineering Principles

- Prefer deterministic, evidence-based diagnosis.
- Do not present correlation as causation.
- Fail safely when GitHub APIs, logs, or local Git data are unavailable.
- Avoid introducing paid or mandatory external services.
- Preserve the versioned diagnosis output schema unless a deliberate schema change is documented.
- Keep workflow permissions to the minimum required scope.

## Pull Requests

Pull requests should include tests where practical and should not contain secrets, credentials, or unrelated formatting changes.
