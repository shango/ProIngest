# ProIngest (working name)

VFX turnover ingest and conform tool for a small studio pipeline. macOS (Apple Silicon) first, Windows later.

The repo began as a PRD package to be handed to Claude Code. It is now an implementation:
the core, the naming and planning, and the render pipeline are built and tested, and a
scanned turnover renders end to end from the command line. There is no user interface yet.
`PROGRESS.md` section 1 is the current state.

## Reading order

1. `CLAUDE.md` - shared context and working rules for Claude Code
2. `PROGRESS.md` - what is actually built, what is next, and every decision taken so far. Start at section 1
3. `PRD.md` - product requirements, scope, user flow, milestones
4. `docs/NAMING_SPEC.md` - clip name parsing and deliverable naming (the contract with the shooters)
5. `docs/COLOR_AND_FORMAT.md` - codecs, color handling, resolution, frame math
6. `docs/QC_RULES.md` - every validation and QC check, with severity
7. `docs/UI_SPEC.md` - screens, list view behavior, keyboard model, theme
8. `docs/ARCHITECTURE.md` - module layout, data model, render pipeline, testing
9. `docs/PACKAGING.md` - installer, ffmpeg bundling, settings and log locations
10. `docs/MAC_SESSION.md` - the residue that cannot be checked without a Mac, and the plan for it
11. `docs/OPEN_QUESTIONS.md` - items still to confirm with the studio. Claude Code should treat these as blockers only where marked.

## Source documents

- `docs/Shooters Resources & Guidelines - Specs + Resources-2.pdf` - the deliverable spec the shooters work from
- `docs/Shooters Resources & Guidelines - Specs + Resources.csv` - the same sheet exported to CSV. Read this one: it needs no viewer, and `docs/NAMING_SPEC.md` section 3 lists the five defects it contains
