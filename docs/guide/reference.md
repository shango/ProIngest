# The window, part by part

Everything the quickstart skimmed over. Read the part you are in rather than the whole thing.

Shortcuts are written the way the Mac draws them: **⌘R** is the Command key and R.

## The layout

![The shot list](images/shot-list.png)

Five things, and they do not move:

- **The toolbar** along the top, in three groups: the batch, the turnover, the run.
- **The batch bar** under it, carrying the batch's name, the search box, the delivery root
  and the In/Out display buttons.
- **The shot list** in the middle, which is where the work happens.
- **The metadata pane** on the right, read only. **⌘I** hides and shows it.
- **The tabs** along the bottom: Issues and Log.

## The toolbar

One sentence each, the same sentences the buttons themselves show when you hover them.

| button | what it does |
|---|---|
| **New** | Starts an empty batch, offering to save the one on screen first. |
| **Open...** | Opens a saved .pibatch file in place of what is on screen. |
| **Save** | Writes the batch to its .pibatch file, asking where the first time. |
| **Add Turnover** | Adds a turnover folder and scans it straight away. |
| **Scan** | Re-tries only the turnovers that came back with no shots. |
| **Ingest Colour Session** | Writes a colour session's approved cut, CDL and CLFs onto one turnover. |
| **Run** | Renders every shot that is not skipped, then writes both spreadsheets. |
| **Stop** | Stops the run. What is in flight finishes; nothing further starts. |
| **Export** | Writes the QC log and the shot tracker without rendering. |
| **Settings** | Opens the settings page: thresholds, naming, colour and logging. |

**A greyed button says why it is greyed.** Hover it. "No batch is open", "A scan is going",
"Every turnover already has shots" - that is usually the whole answer, and it is the reason the
toolbar shows everything from the first launch rather than hiding what cannot be used yet.

**Run is the exception worth knowing.** It is not greyed when a turnover has no colour session
ingested, because it will run: it refuses every turnover and writes nothing, which is correct
and looks exactly like a dead button. Its tooltip says so first.

**Export writes the two spreadsheets without rendering anything.** A run writes them when it
finishes too; Export is for the batch as it stands now - after a scan, to hand the QC log
round before anything is delivered, or after an edit, to refresh them. It re-runs every check
first, asks for the delivery root if there is none, and the banner above the list says where
the files went.

## The shot list

One row per shot, grouped under a header naming the turnover folder and counting what is under
it. **Space** on a header collapses it. Order is timeline order within a turnover and cannot be
changed; **⌘F** and the search box narrow the list to a shot code fragment, keeping the header
above whatever survives.

The first three columns - the dot, Shot and Elem - **stay put while the rest scrolls sideways**,
so a row can still be identified while reading a column at the far right of it.

| column | what it is |
|---|---|
| dot | the row's state, below |
| **Shot** | the shot code. **Yours to edit** |
| Elem | which element of the shot this is: `pl` main plate, `cp` clean plate, `el` element, `wit` witness cam, `re` recon |
| Source | the media file the timeline clip resolved to |
| Res | its resolution |
| FPS | its frame rate |
| **In** | first delivered frame. **Yours to edit** |
| **Out** | last delivered frame. **Yours to edit** |
| Dur | how long the delivery is, from In and Out |
| Max | how much there is to work with, handles included |
| Audio | whether sound was found, and how much |
| Side | which extras were found: HDRI, camData, stills |
| Ver | which version this shot is at |
| Progress | jobs done over jobs planned, during a run |
| **Notes** | free text, and it goes to the tracker. **Yours to edit** |

### The dot

| dot | means |
|---|---|
| grey | nothing wrong, nothing delivered yet |
| amber | a warning, and the row is tinted faintly |
| red | an error: this row is blocked and will not deliver |
| hollow | you skipped it |
| accent | rendering now |
| green | delivered |
| red, tinted | the render failed |

Hover a row for the rule IDs and messages behind its state. Click the dot to jump to that row
in the Issues tab.

### Frames or timecode

The three buttons in the batch bar - **Frames**, **Source TC**, **Record TC** - set what In and
Out show, and **⌘T** cycles them. Whichever is not showing sits under it in smaller text, so
nothing is ever hidden, only demoted.

**Frames is the default and is what the tool actually holds.** Frame maths is whole numbers
throughout: In and Out are frame numbers, the checks quote them, and the delivered EXR sequence
is numbered by them. Timecode is worked out at the edges and never stored. The choice is
remembered with the batch, so working in source TC is something you set once.

## Editing a shot

Four cells in a row are yours: **Shot**, **In**, **Out** and **Notes**. Everything else is read
off the media, worked out from those four, or written by a run.

- Click a cell and type. There is no key to press first.
- **Tab** and **Shift+Tab** walk the four, wrapping into the next row.
- **Enter** commits and stays. **Escape** puts the cell back.
- **⌘K** skips the row, asking why the first time. A skipped row is not delivered and the
  reason reaches the QC log.

**In and Out take three kinds of value** and work out which you meant:

| you type | it means |
|---|---|
| `1024` | that source frame |
| `01:00:12:04` | that timecode, read as source or record to match the display |
| `+12` or `-8` | that many frames from where it is now |

Anything else turns **red in the cell as you type it** and changes nothing when you leave.
A half-typed value is somebody still typing, not somebody asking for something impossible.

Committing recomputes Dur and Max, re-runs the checks **for that row only**, which is what keeps
typing instant, and saves a moment later. A batch that has never been saved asks for a name on
**⌘S** or when you close the window.

## The metadata pane

![The metadata pane](images/metadata-pane.png)

Everything known about the selected shot that has no column: codec, pixel format, start
timecode, file sizes, the camera data, the turnover, and the paths themselves. Nine sections -
Identity, Source media, Frame rate, Range, Colour, Audio, Side files, Turnover and QC - each
collapsible and each remembering whether you shut it.

- **Read only**, always. The list owns every edit, so there is one place a value can be changed
  and one place validation can disagree with itself.
- **It never takes focus.** Tab keeps cycling the four editable cells, and the pane is reachable
  by mouse and by ⌘I only.
- **Every value copies.** Select it with the mouse, or use the **Copy** button beside a path -
  which is the honest way to get a long one, since selecting a shortened path would copy the
  ellipsis with it. **Copy all** puts the whole pane on the clipboard as `key: value` text.
  Long paths shorten in the middle, because the filename is the part that identifies the file.
- **Select several shots** and it shows what they agree on and marks the rest `mixed`. That is
  how one clip at the wrong resolution in a turnover of thirty is found without reading thirty
  rows.
- Its **Colour** section is where you check that a shot got the CLF you expected: it names the
  source encoding, where that name came from, and the CLF itself.

## The Issues tab

![The Issues dock](images/issues-dock.png)

Every check that fired, with the row it is about, its rule number, whether it is an error or a
warning, and the full message. **Double-click a line to select that shot in the list.**

Rule numbers are stable and never change meaning, so `QC-030` means the same thing in the
window, in the log and in the spreadsheet. `docs/QC_RULES.md` is the full list.

Checks run in two passes. The first is about the turnover **before** anything is written -
format, resolution, ranges, handles, audio, side files - and re-runs every time you edit a row.
The second is about each delivered file the moment it lands, and it is the one that catches a
render that went wrong rather than a source that arrived wrong.

## The Log tab

![The Log tab](images/log-tab.png)

Time, level, shot and message, over a filter bar: a minimum level, a search box, and
**Selected row only**.

- **Every ffmpeg command line is in here verbatim**, which is what makes a render reproducible
  by hand. Messages are never shortened and never re-wrapped, and **⌘C** copies what is
  selected.
- **Selected row only** shows what happened to one shot. Only lines a render worker stamped
  carry a shot, so it hides what the window itself logged too: it answers "what happened to this
  shot", not "what happened while this shot was selected". It is unavailable with no selection
  or a selection spanning two shots.
- **The panel is bounded and the file is not.** It keeps the last few thousand lines; the
  complete record is the rotating file in `~/Library/Logs/ProIngest`, which Settings names.
- It follows the newest line **only when it is already at the bottom**, because somebody who has
  scrolled up is reading something.

## The run

![A run in progress](images/run-in-progress.png)

**⌘R.** If the delivery root is not set it asks once, then plans the batch, works out which
version this run writes, and renders through several processes at once.

Four things describe the run and each says something the others cannot:

- **The bar above the list** is the whole batch.
- **The line under it** names the step happening now: checking, planning, each deliverable as it
  is written, then verifying and writing the spreadsheets. It names the job that has been going
  longest and keeps naming it until it finishes, rather than chasing whichever spoke last.
- **Each row's Progress column** is that shot's own jobs, as `3/5`.
- **The status bar** carries the percentage, how many jobs are going, frames per second and the
  time left.

**⌘.** stops. What is in flight finishes and nothing further starts, which can take a minute or
two if a reference encode is going. What did land is recorded rather than forgotten: the banner
says `Run stopped` rather than `Batch complete`, and the rows say how many of their deliverables
are missing.

**A version is resolved once per shot, per run.** A shot delivered at v01 comes back at v02, and
the whole shot moves together rather than one deliverable at a time.

**Every file is written to a temporary name and renamed when it is complete**, so a crash never
leaves something that looks finished. A file that fails its checks is **kept** and marked,
because a file that failed a check is evidence; one that never finished is deleted.

## Settings

![The settings page](images/settings.png)

Sections on the left, the form on the right, Apply and Cancel at the bottom. It is the one
button that opens with no batch loaded, because it is where a new batch's numbers come from.

| section | what is in it |
|---|---|
| General | how many shots render at once, and a media path rewrite for timelines exported on Windows |
| Rules | every threshold the checks compare against: shortest and longest shot, expected handles, expected resolution, audio sync tolerance |
| Colour | where the Ingest chooser opens, and a read-only view of the ACES config, the output transform and the input transform table |
| Naming | the pattern every clip name is parsed with and every delivered name is built from |
| Output | the reference mp4's quality and the EXR compression level |
| Advanced | how much is logged, an ffmpeg to use instead of the bundled one, and where the log file is |

Three things are worth knowing about it.

**Changing a threshold re-checks the open batch immediately**, so the list and the Issues tab
describe it under the numbers now in force.

**The thresholds live in two places on purpose.** Settings holds the numbers a *new* batch
starts from, and each batch keeps its own copy from the moment it is made. Changing them next
month therefore cannot silently re-judge a batch that shipped last week.

**A value that will not parse changes nothing**, rather than being corrected to something
plausible - the same rule as In and Out.

There is **no colour mode and no source encoding setting**: each clip's own metadata names what
it is encoded in. And where the colour session lives is not here either - it is ingested per
turnover and kept with the batch, because it is a record of what that work was rendered from
rather than a preference.

## Every shortcut

| key | does |
|---|---|
| **⌘N** | new batch |
| **⌘O** | open a batch |
| **⌘S** | save the batch |
| **⌘F** | jump to the search box |
| **⌘I** | show or hide the metadata pane |
| **⌘T** | cycle Frames, Source TC, Record TC |
| **⌘K** | skip the current shot |
| **⌘R** | run |
| **⌘.** | stop |
| **⌘C** | copy the selected lines, in the Log tab |
| Tab, Shift+Tab | the next and previous editable cell |
| Enter, Escape | commit, revert |
| Space | collapse or expand a turnover header |
| Arrows | up and down the shots, skipping headers |
