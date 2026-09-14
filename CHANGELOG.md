# Changelog

All notable changes to CI Detective are documented here.

## [0.1.0] - 2026-09-14

### Added

- Deterministic diagnosis of failed GitHub Actions jobs.
- Multi-job failure reporting.
- Job-specific log retrieval with isolated fallback behavior.
- Full Git history support in validation workflows.
- Regression correlation using traceback and changed-file evidence without claiming causation.
- Paginated remote commit file analysis.
- Paginated pull request comment lookup.
- Versioned JSON diagnosis output (`schema_version` 1.0).
- Action outputs for diagnosis, confidence, and schema version.
- Bounded subprocess execution and observable remote-analysis failures.
- Resilience regression tests.
- Scoped GitHub Actions write permissions.
- Initial security, contribution, and release documentation.

### Security

- Reduced workflow write permissions to the detective job that needs PR/issue comment access.
- Documented limitations for fork pull requests.

[0.1.0]: https://github.com/SamoTech/CI-Detective/releases/tag/v0.1.0
