# ProIngest (working name)

VFX turnover ingest and conform tool for a small studio pipeline. Windows first, macOS later.

This repo starts as a PRD package intended to be handed to Claude Code for implementation.

## Reading order

1. `CLAUDE.md` - shared context and working rules for Claude Code
2. `PRD.md` - product requirements, scope, user flow, milestones
3. `docs/NAMING_SPEC.md` - clip name parsing and deliverable naming (the contract with the shooters)
4. `docs/COLOR_AND_FORMAT.md` - codecs, color handling, resolution, frame math
5. `docs/QC_RULES.md` - every validation and QC check, with severity
6. `docs/UI_SPEC.md` - screens, list view behavior, keyboard model, theme
7. `docs/ARCHITECTURE.md` - module layout, data model, render pipeline, testing
8. `docs/PACKAGING.md` - installer, ffmpeg bundling, settings and log locations
9. `docs/OPEN_QUESTIONS.md` - items still to confirm with the studio. Claude Code should treat these as blockers only where marked.

## Source documents

- `Shooters_Resources__Guidelines__Specs__Resources2.pdf` - the deliverable spec the shooters work from (copy into `reference/` when setting up the repo)
- `VFX_Ingest_Tool_Proposal_1.pdf` - original proposal (copy into `reference/`)
