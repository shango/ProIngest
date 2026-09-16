# Session close, 16 September 2026 (the Mac, and getting a build to a person)

**This file is disposable and it is not the handoff record.** `PROGRESS.md` section 1 is, and it
is written to be picked up cold. This is a note about what one session did, kept because context
is being cleared. Delete it once it has been read. **If it disagrees with `PROGRESS.md` or the
docs, they win.**

It replaces the previous file of the same name, which closed on the `MainWindow` split.

## The one paragraph version

**No behaviour changed and no core code was touched.** The session was about getting the tool
onto a Mac and then onto the editor's Mac, driven by somebody working against a rented-box
clock. Two shell scripts: **`build/mac_build.sh`**, which is a fresh clone to a built app and
dmg in one command, and **`ProIngest.command`**, which is the same folder run without building
anything. **All five PRs are merged and `main` carries everything** - a fresh clone needs no
`git checkout`. **1697 tests**, `ruff`, `ruff format` and `mypy --strict` clean, CI green on
`main` (run 35144687967). Build Track republished, version 63.

## What a new session should know first

**`main` is the branch.** PRs #2 through #5 all merged on 16 September. `m7/packaging`,
`m9/guide-and-settings`, `docs/post-merge-state` and `m7/command-launcher` still exist on the
remote, fully merged, and deleting them is safe.

**A Mac needs one command.** `git clone`, then `bash build/mac_build.sh` to build or
`./ProIngest.command` to just run it. `docs/MAC_SETUP.md` section 0 is the first and 0.5 is the
second; the rest of that document is the same thing by hand and is what to read when a step
fails.

**Neither script has ever run on macOS.** Everything in them is a line CI runs and the document
already carried, but the wrappers have only ever been parsed here. `docs/MAC_SESSION.md` opens
with them.

## The two things worth not re-deriving

**GitHub does not retarget a stacked PR when its base merges. It does it when the base branch is
deleted.** This repository does not delete on merge, so PR #3 sat pointing at `m7/packaging`
after #2 went in, and `PROGRESS.md` had said for two days that it would sort itself out. Worse,
**`gh pr edit --base` fails on this repository** with a Projects (classic) GraphQL deprecation
error that has nothing to do with the base branch. The REST call works:

```
gh api -X PATCH repos/shango/ProIngest/pulls/<n> -f base=main
```

**An `.app` is a folder.** The question "can it run from a downloaded folder rather than an
executable" took half an hour to answer because both sides meant different things by folder.
macOS draws a bundle as a single icon, so the folder that runs with nothing installed is
`dist/ProIngest.app` and there was never a third thing to build. `docs/MAC_SETUP.md` section 0.5
is now a table of the two, and the distinction it turns on is that `ProIngest.command` needs
`uv` and a network on first use and the app needs neither.

## Handing a build to the editor

`PROGRESS.md` section 5 has the full list under "Getting a build to the editor: what is actually
known". The three that cost the most:

- **Quarantine is applied by the receiving app**, so the file's history before it reaches their
  Mac is irrelevant. `gh` and `curl` do not set it; browsers and AirDrop do; `scp`, `rsync`, USB
  and mounted shares do not.
- **A zip drops the executable bit and symlinks**, which destroys an `.app` and makes the
  launcher unrunnable - but **a dmg inside a zip is safe**, because it is one opaque file. That
  is the distinction that matters when a build goes on Drive.
- **The dialog says the app is damaged and the default button deletes it.** Instructions sent
  with a build have to say Cancel before they say anything else. A walkthrough was written for
  the editor in chat this session and **was deliberately not committed** - the user said it was
  fine as it was. `docs/guide/install.md` covers the refusal but assumes a bare dmg, mentions no
  zip and does not warn about that button. Worth folding in when OQ-49 settles the guide's form.

## What is next

`PROGRESS.md` section 1's "Next task" is the list and it is current. In one line each:

- **A person:** OQ-9, which is now the whole of the handover problem; OQ-49, the guide's form;
  and asking OQ-44 and OQ-46.
- **This machine:** nothing.
- **The Mac:** `docs/MAC_SESSION.md`, which now opens with three lines this session added - the
  two scripts, and whether a dmg arriving through the **Google Drive mount** carries quarantine.
  That last one is ten seconds and decides whether the editor ever has to open Terminal.
- **A real turnover and a real colour session:** the whole of M8.

## One loose end that is not a task

The user dropped a sample export folder in the repo root, `TEST0001/`, on 16 September. **Eight
of its nine folders are exactly what the tool already writes.** The ninth is `TEST0001_lidar`,
and lidar is an explicit v01 non-goal in `PRD.md`. The user said the sample was information
rather than a request, so nothing was built. It is untracked and git cannot commit empty
directories, so it exists on that machine only; `PROGRESS.md` section 5 has the detail.
