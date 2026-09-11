# Interface preview

A front-end mock of `docs/UI_SPEC.md`, built so the layout can be argued about before any
of it is written in Qt. It exists for one reason: showing producers what the tool will look
like without waiting for M5.

## Running it

Open `index.html` in any browser. There is no build step, no `npm install`, and no server.

It is one file. React 18 and Babel load from cdnjs, so the machine opening it needs a
network connection the first time; everything else, including all the data, is in the file.

To send it to someone who should not have to open a folder at all, use the published link
in `PROGRESS.md` section 8 instead.

## What is real and what is not

**Real**, taken from the spec rather than invented:

- The window layout, in the order `UI_SPEC.md` section 1 sets out: toolbar, batch bar, shot
  list, metadata pane, bottom dock, status bar.
- The columns and the frozen left three, section 2. The secondary timecode line under In and
  Out, and the Source/Record toggle that switches which one is primary.
- Row colours and the status dot, section 3.
- The metadata pane's sections and their fields, section 12, including that it is read only.
- Arrow keys move the selection, Cmd+T toggles timecode, Cmd+I hides the pane. Section 4.
- Rule IDs and their wording come from `docs/QC_RULES.md`. Deliverable names come from
  `docs/NAMING_SPEC.md` section 3.
- Source root and delivery root are the two folder choosers OQ-25 settled.

**Not real.** Every shot code, turnover, shooter name, path, file size and duration is
invented. Nothing is scanned, rendered, probed or written. Run animates a progress bar and
writes no files. The shipping application is PySide6; this is a web page that imitates it.

## Keeping it honest

This is a mock, not a second implementation, and it is not wired to anything in
`proingest/`. If the spec changes and this disagrees with it, the spec wins and this is
stale. Do not let anyone read a behaviour off this page that `docs/UI_SPEC.md` does not
state.
