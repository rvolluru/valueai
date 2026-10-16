# Repository instructions

## Keep analysis-process documentation current

`docs/LISTING_ANALYSIS_PROCESS.md` is the authoritative functional description of
Jouft's listing analysis workflow. Whenever an implementation change affects that
workflow, update this document in the same commit as the code change.

This includes photo coverage and evidence selection, identification and model
handoffs, prompts that change behavior, analysis/identity reuse and invalidation,
condition-specific pricing and fallbacks, mannequin generation and image review,
photo cleanup, manual review, and analysis-related user actions/publication rules.

- Describe actual implemented behavior, not merely the intended design.
- Keep the document's updated date and implementation/deployment status accurate.
  Clearly label changes that are implemented but not deployed; update status after
  a verified deployment. Do not present local changes as production behavior.
- Update affected flow diagrams, decision rules, model/input/output tables and API
  descriptions as necessary. Keep reliability investigations in separate documents.
- Version the document through Git commits, not duplicate dated copies. Use clear
  commit messages so GitHub history explains how the process changed.
- Documentation-only maintenance does not authorize deployment or unrelated code
  changes. Preserve unrelated worktree changes.
