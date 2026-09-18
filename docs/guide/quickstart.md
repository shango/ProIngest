# Quickstart

One turnover, from opening ProIngest to the two spreadsheets. About a page. Read it once;
after that the tool tells you what to do next from the buttons themselves.

Shortcuts are written the way the Mac draws them: **⌘R** is the Command key and R.

The install section covers getting the app onto the Mac, and the reference section is the
part-by-part version of everything skimmed over here.

## Before you start

Three things have to exist, and only the third one usually does not.

- **The turnover folder**, as the shooters delivered it: one file per shot, the `.otio`
  timeline, and the per shot extras. It can be on a Drive mount, an external volume or the
  local disk, and ProIngest does not care which.
- **Somewhere to deliver to.** Any folder you can write into. The show and shot folders are
  made under it.
- **The colour session's exports**: the final `.edl` and one `.clf` per shot. **Nothing final
  renders without them** and that is deliberate, not a limitation - see "When Run refuses"
  below. Scanning and checking a turnover works fine before they arrive.

## The seven steps

![The window before a batch is open](images/empty-state.png)

**1. Add the turnover.** Press **New batch** and pick the turnover's own folder in the chooser
that opens; **Add Turnover** in the toolbar is the same chooser for the next one. The scan
starts immediately - you do not press Scan afterwards, and Scan is for something else. It runs
in the background, so the window stays usable, and the shots appear grouped under the folder's
name as they are found.

A batch can hold several turnovers. Press Add Turnover again for each.

**2. Read the list.**

![The shot list](images/shot-list.png)

One row per shot, grouped by turnover. The coloured dot at the left of each row is its state,
and a row with something wrong is tinted. Anything you want to know about the selected shot
that has no column - codec, timecode, file sizes, the camera data, the paths themselves - is
in the pane on the right (**⌘I** hides and shows it).

Everything the checks found is in the **Issues** tab along the bottom, each with its rule
number. Double-click a line to jump to the shot it is about.

![The Issues dock](images/issues-dock.png)

**3. Fix what is worth fixing.** Four things in a row are yours: the shot code, In, Out and the
notes that go to the tracker. Click a cell and type. In and Out take a frame number, a timecode,
or a nudge like `+12`; a value that cannot be read turns red as you type it and changes nothing.
**⌘T** cycles In and Out between frames, source timecode and record timecode.

**⌘K** skips a shot and asks why. A skipped shot is not delivered and the reason reaches the
QC log.

Every edit re-checks that row and saves itself a moment later, so there is nothing to remember
to press. **⌘S** names the batch file the first time.

**4. Ingest the colour session.** If the colourist exported it by the convention - a folder
named exactly as the turnover folder, inside a `_color` folder beside the turnovers, holding
the final `.edl` and the `.clf` files - the scan finds it and asks whether to ingest it. Say
yes. Otherwise select the turnover (or any shot under it), press **Ingest Colour Session**,
and point at the session's final `.edl`. One turnover at a time: another one can still be
waiting on colour while this one delivers.

What it writes onto the rows: the approved In and Out from the trim the colourist and the AD sat through,
the CDL as the readable record, and which `.clf` each shot is graded with. It then tells you how
many shots matched, how many got a CLF, and the three lists worth looking at - shots the session
says nothing about, trims the approved cut overwrote, and shots that more than one CLF claims.

**The approved cut wins over a trim you already made**, and the report names the rows that lost
one. Trimming again afterwards is allowed; it is what step 3 is for, and any row that moved is
flagged in the QC log as delivered at something other than what was approved (QC-045).

**5. Say where it goes.** In the bar above the list, click **Set delivery root...** and pick the
folder. The button is amber until there is one and shows the path after that. It is remembered
with the batch, so reopening a `.pibatch` months later restores it.

**6. Run.** **⌘R**. It plans the batch, works out which version this run writes, and renders
through several worker processes at once.

![A run in progress](images/run-in-progress.png)

A bar above the list carries the whole batch, a line under it names each step as it happens,
each row fills its own bar as its deliverables land, and the status bar carries the percentage,
how many jobs are going, frames per second and the time left. **⌘.** stops: what is in
flight finishes and nothing further starts, and what did land is recorded rather than forgotten.

**7. Read the banner.** When it ends: `Batch complete: 14 done, 0 failed, 0 skipped`, and a
link to where the two spreadsheets went. Click it to open the folder.

## What you get

Under the delivery root, `<show>/<shot>/` per shot:

| | |
|---|---|
| plates | 4k and HD EXR sequences, graded, scene linear ACEScg, frames numbered from 1001 |
| references | 4k and HD H.264 mp4, viewable, with the shot's audio on them |
| audio | the wav, cut to the delivered range |
| extras | HDRI, camData and the reference stills, copied and renamed to spec |

And under `<show>/_reports/`, two spreadsheets, each named for the batch and the day it was
written. `shot_tracker_...xlsx` is rows to paste into the production's own tracker, and it fills
only the columns that are the tool's to fill - the thirty the vendor's team maintains are not
touched. `qc_ingest_log_...xlsx` is the full report: every shot, every delivered file, and a
column per check reading pass, fail or NA.

Every deliverable is checked the moment it lands. One that fails is **kept**, marked, and
listed in the Issues tab, because a file that failed a check is evidence. One that never
finished is deleted, so a crash never leaves something that looks complete.

## When Run refuses

The commonest one is not a fault. **A turnover with no colour session ingested renders
nothing** (QC-008) - the plates would be missing the approved look, and delivering them
ungraded is worse than delivering them late. Run says so in its tooltip before you press it,
and if every turnover in the batch is in that state it opens a dialog naming each one and the
rule holding it back, then brings up the Issues tab, rather than starting a run that does
nothing. One turnover waiting on colour beside one that is ready is only a line in the status
bar, and the ready one delivers.

Otherwise: hover any greyed button and it says why it is greyed. That is what the tooltips are
for, and it is usually the whole answer.

## If something looks wrong

The **Log** tab is everything the tool did, including **every ffmpeg command line verbatim**, so
a render can be reproduced by hand. Filter it by level, by text, or to one shot. **⌘C** copies a
command whole, and it is never shortened or re-wrapped.

The same thing is written to a file, kept for a fortnight, and Settings' Advanced section says
where.
