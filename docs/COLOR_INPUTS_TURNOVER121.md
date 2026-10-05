# What the tool reads for colour: Turnover121

Traced 2026-09-25 against `turnover121_09_23_2026_danielluckett`. I ran the real scan and planner on the folder and probed every `.mov` with ffprobe. Nothing was rendered.

| Source | What it says for every Turnover121 clip | How the tool uses it |
|---|---|---|
| The file's own tags (ffprobe) | h264 yuv420p, 8-bit, 3840x2160; matrix bt709, range `tv` (limited), transfer bt709, primaries bt709; encoder tag DaVinci Resolve Studio | Only the **matrix and range**, for turning YUV into RGB. The transfer and primaries tags are ignored. |
| CSV `Input Color Space` | `Apple Log` for every clip (the notes columns are absent) | The **source encoding**, meaning both the curve and the gamut (`scan.py:268`, via `MetaRow.written_encoding`) |
| EDL `*ASC_SOP` / `*ASC_SAT` | slope **4.886003**, offset 0, power 1, sat 1 on all 11 events | **The grade** |
| Assumed, not read | ACES 2.0 built-in studio config (1.3 until 2026-09-25), ACEScct working space, ACEScg plate space, sRGB display, "ACES 2.0 - SDR 100 nits (Rec.709)" view | Constants in `color.py` |

`Apple Log` is a colour space the pinned config knows directly. Its transform is Apple's own Apple Log to ACES2065-1 (in the ACES 1.3 config, `IDT.Apple.AppleLog_BT2020`, so BT.2020 primaries), so no table lookup is involved.

There's a conflict here that is still open from 2026-09-24. The files are Resolve renders labelled BT.709 everywhere, while the CSV calls them Apple Log. The tool believes the CSV for the curve and gamut, and the tags for the YUV matrix. Nobody has confirmed whether Resolve's render converted the pixels or only relabelled them.
