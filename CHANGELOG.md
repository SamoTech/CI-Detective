# Changelog

All notable changes to CI Detective are documented here.

## [Unreleased]

### Added

- Optional NVIDIA AI enhancement using live model availability checks.
- Capability-based NVIDIA free-model selection for coding/reasoning workloads.
- Same-API model fallback when the selected NVIDIA model is unavailable or fails.
- Advisory AI output that never overrides the deterministic diagnosis.
- Customer-facing Markdown report generation and delivery.
- Repository report publication when `contents: write` is explicitly available.
- GitHub Actions artifact fallback when repository publication is unavailable.
- Report-related Action outputs: `report_path`, `report_url`, and `report_status`.
- Expanded user documentation covering setup, permissions, reports, AI configuration, outputs, troubleshooting, and security.

### Reliability

- NVIDIA availability or request failures do not break deterministic CI diagnosis.
- Report persistence failures remain non-fatal and preserve the workflow fallback path.

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
