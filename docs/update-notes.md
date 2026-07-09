# Update Notes

## 2026-07-09: Connected Agent Documentation Refresh

This update makes the current Agent Decision Bridge product language consistent
across the repository.

### What Changed

- Consolidated the public product description around two modes:
  **Ask First** and **Connected Agent**.
- Added `docs/user-guide.md` as the main user-facing guide.
- Renamed the non-technical Connected Agent flow to
  `docs/connected-agent-user-flow.md`.
- Removed superseded multi-tier drafts and older live-verification notes from
  the public repository.
- Removed platform-upload packaging and promotional card assets from repository
  tracking so the GitHub repository stays focused on Agent Decision Bridge.
- Removed stale model/version wording from current docs and user-visible
  helper output.
- Added the `scripts/connected_agent_flow.py` product wrapper as the preferred
  consultation entry point.
- Updated Connected Agent tooling docs and tests for:
  `open_default_workspace`, bounded `read_lines`, and normal source-file reads
  up to 1 MB.

### Current User-Facing Model

- **Ask First**: Codex prepares a focused package for manual advisor review. No
  public connector exposure. Risk `1/5`.
- **Connected Agent**: ChatGPT Web connects to an allowed project window through
  Apps/MCP connector tools. Read/search/list are automatic; write/edit/bash use
  one-action approval by default. Risk `3/5-5/5`.

Older compatibility names remain only where they are needed to explain legacy
CLI modes, test coverage, or migration behavior. They are not current product
documentation.

### Validation

- Current public docs scan clean for superseded model/version wording.
- Checked Markdown links in the current entry documents.
- Ran the full Python test suite:
  `python3 -m unittest discover -s tests`
  result: `170 tests OK`.
