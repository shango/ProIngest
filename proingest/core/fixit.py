"""The Fix-it report: what Ben needs to change, in plain words, as one HTML page.

User, 2026-10-06: a link above the Details dock, named "Fix-it report", opening in the
browser. Written for the colourist rather than the editor: he knows basic editing and
colour, and is not a Resolve expert. So each QC rule he can act on gets a sentence in
his terms (`ADVICE`), every clip it applies to is listed once under it, and the rule IDs
stay out of sight. Rules about the editor's own choices (In/Out edits, the delivery
root, a run) are not his and are left out.

Built from the QC results already on the batch, so the page says what the Issues dock
says. The page is self-contained: no fonts or scripts from anywhere, because it is
opened from disk and sent on as a file.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal, NamedTuple

from proingest import __version__
from proingest.core import exports, models, naming, qc
from proingest.core.models import Batch, QCResult, ShotRow, Turnover

Where = Literal["resolve", "folder", "look"]

SECTIONS: dict[Where, str] = {
    "resolve": "Fix in Resolve",
    "folder": "Fix in the turnover folder",
    "look": "Worth a look",
}
"""Where each fix happens, in the order the page shows them."""


@dataclass(frozen=True)
class Advice:
    where: Where
    title: str
    """What is wrong, as a short sentence."""

    explain: str
    """Why it matters and what to do, in a sentence or two."""

    detail: Literal["none", "message", "range", "handles"] = "none"
    """What each listed clip adds: nothing, the tool's own message, how far the cut
    misses the file (QC-029), or which side is short of spare frames (QC-030)."""


ADVICE: dict[str, Advice] = {
    "QC-001": Advice(
        "resolve",
        "The EDL or the metadata CSV is missing.",
        "Every turnover folder needs both, exported from the timeline: the EDL (the cut) and the "
        "metadata CSV (which clip belongs to which shot). Please export the missing one into the folder.",
        "message",
    ),
    "QC-002": Advice(
        "resolve",
        "The EDL or the metadata CSV cannot be read.",
        "The file is damaged or is not the usual export. Please export it again from the timeline.",
        "message",
    ),
    "QC-004": Advice(
        "resolve",
        "The EDL or the metadata CSV is empty.",
        "Please export it again from the timeline with the clips on it.",
        "message",
    ),
    "QC-008": Advice(
        "resolve",
        "None of the clips has its colour file (AMF).",
        "Each clip on the timeline needs its own AMF, exported from the same timeline. The AMF tells "
        "the tool which camera colour space the clip is in and what its grade is; without it nothing "
        "can be converted.",
    ),
    "QC-010": Advice(
        "resolve",
        "A clip's Shot or Shot Type cannot be used.",
        "The Shot needs to look like SECA0012, and the Shot Type has to be one the tool delivers: "
        + ", ".join(t + "01" if t in naming.ELEMENT_TYPES else t for t in naming.CLIP_TYPES)
        + " or HDRI. Please correct it in the clip's metadata.",
        "message",
    ),
    "QC-011": Advice(
        "resolve",
        "Two clips would be delivered under the same name.",
        "They have the same Shot and Shot Type. Please give one of them the next number (pl02 instead "
        "of pl01, for example).",
    ),
    "QC-029": Advice(
        "resolve",
        "The cut uses frames the camera file does not have.",
        "The EDL asks for frames from before the file starts or after it ends. This usually means the "
        "clip on the timeline is linked to a different file, such as a proxy copy. Please relink it to "
        "the camera original, then export the EDL and AMFs again.",
        "range",
    ),
    "QC-033": Advice(
        "resolve",
        "A plate is too short.",
        "Plates have a minimum length. Please lengthen the cut on the timeline.",
        "message",
    ),
    "QC-034": Advice(
        "resolve",
        "A plate is too long.",
        "Plates have a maximum length. Please shorten the cut on the timeline.",
        "message",
    ),
    "QC-046": Advice(
        "resolve",
        "A clip's colour file (AMF) does not say what colour space the camera recorded in.",
        "Without it the tool cannot convert the clip. Please check the clip's input colour space in "
        "Resolve and export its AMF again.",
    ),
    "QC-047": Advice(
        "resolve",
        "A clip's colour file (AMF) names a camera colour space the tool does not know.",
        "Please check the clip's input colour space in Resolve. If it is right, let the editor know "
        "which camera this is.",
        "message",
    ),
    "QC-065": Advice(
        "resolve",
        "The two Shot Type columns in the metadata disagree.",
        "The metadata has two Shot Type columns and they say different things for this clip. Please "
        "make them match.",
    ),
    "QC-066": Advice(
        "resolve",
        "A clip with a Shot Type is not in the cut.",
        "The metadata gives it a Shot and Shot Type, but no event in the EDL uses it. Please put it on "
        "the timeline, or clear its Shot Type if it is not meant to be delivered.",
    ),
    "QC-067": Advice(
        "resolve",
        "The tool cannot tell which cut belongs to which clip.",
        "Either this clip is used twice in overlapping places, or two clips share the same timecode. "
        "Please make sure each clip is used once on the timeline.",
    ),
    "QC-071": Advice(
        "resolve",
        "The ALE does not match the EDL.",
        "Please export the ALE again from the same timeline, or take it out of the folder.",
    ),
    "QC-073": Advice(
        "resolve",
        "A clip is sped up, slowed down or reversed.",
        "VFX plates are delivered at normal speed. Please remove the speed change. A freeze frame is fine.",
    ),
    "QC-075": Advice(
        "resolve",
        "A clip has no colour file (AMF), or the one there is for a different clip.",
        "Each clip on the timeline needs its own AMF, exported from the same timeline as the EDL. The "
        "AMF tells the tool which camera colour space the clip is in and what its grade is; without it "
        "nothing can be converted.",
    ),
    "QC-076": Advice(
        "resolve",
        "A grade file (CLF) is missing or was changed after export.",
        "The clip's AMF points at a CLF that is not in the folder, or no longer matches. Please export "
        "the clip's AMF and CLFs again, together.",
        "message",
    ),
    "QC-077": Advice(
        "resolve",
        "Part of a clip's grade will be left out.",
        "The AMF carries a look the tool does not apply; only the main grade (the CLF) is used. Please "
        "check the shot still looks right without it.",
        "message",
    ),
    "QC-079": Advice(
        "resolve",
        "A clip's colour file (AMF) names a viewing setup the tool does not know.",
        "The AMF's output transform (what the grade was viewed through) is not one the tool recognises. "
        "Please check the project's output colour space.",
        "message",
    ),
    "QC-082": Advice(
        "resolve",
        "The grade came without its CLF file.",
        "The tool uses the simpler colour correction (a CDL) stored in the AMF instead, so the shot is "
        "still graded. Please export the CLFs with the AMFs next time.",
    ),
    "QC-012": Advice(
        "folder",
        "A clip is not in the turnover folder.",
        "The metadata lists it, but no file with that name is in the folder. Please copy it in, or put "
        "the camera original on the timeline instead.",
    ),
    "QC-013": Advice(
        "folder",
        "Two files in the folder match one clip.",
        "There is more than one file with this name. Please remove the extra copy.",
        "message",
    ),
    "QC-014": Advice(
        "folder",
        "A file in the folder cannot be opened.",
        "It may be damaged or only partly copied. Please copy it into the folder again.",
    ),
    "QC-015": Advice(
        "folder",
        "An image sequence has missing frames.",
        "Please copy the sequence into the folder again.",
        "message",
    ),
    "QC-022": Advice(
        "folder",
        "A clip is in a format the tool cannot read.",
        "Camera RAW and some other formats are not supported. Please supply the clip as ProRes.",
        "message",
    ),
    "QC-023": Advice(
        "folder",
        "A clip is not UHD (3840 x 2160).",
        "Plates are delivered at UHD. Please check the clip's resolution.",
        "message",
    ),
    "QC-026": Advice(
        "folder",
        "A clip is not 24 frames per second.",
        "Every clip has to be 24 fps. Please check its frame rate.",
        "message",
    ),
    "QC-027": Advice(
        "folder",
        "A clip has drop-frame timecode.",
        "The project is 24 fps non-drop. Please supply the clip with non-drop timecode.",
    ),
    "QC-041": Advice(
        "folder",
        "More than one sound file matches a plate.",
        "Please keep one sound file per plate in the folder.",
    ),
    "QC-042": Advice(
        "folder",
        "A plate's sound file is missing or cannot be read.",
        "Please copy the sound file into the folder again.",
    ),
    "QC-028": Advice(
        "look",
        "A clip has no timecode.",
        "The tool can still deliver it, but the cut is placed less reliably. Fine if the camera did not "
        "record any.",
    ),
    "QC-030": Advice(
        "look",
        "A cut leaves few or no spare frames (handles).",
        "VFX like a few frames either side of the cut. Fine if intended; otherwise extend the cut on the "
        "timeline.",
        "handles",
    ),
    "QC-040": Advice(
        "look",
        "A plate has no sound.",
        "Fine if it was shot without sound.",
    ),
    "QC-043": Advice(
        "look",
        "A plate's sound is a different length from the cut.",
        "Please check the sound file is the right one for this plate.",
    ),
    "QC-064": Advice(
        "look",
        "Some clips have no Shot Type, so the tool skips them.",
        "Fine for clips that are not deliverables, such as alternate takes. If one should be delivered, "
        "please give it a Shot and Shot Type.",
    ),
}
"""Every rule Ben can act on, in his words. A rule not here is the editor's, or the tool's."""

HDRI_IMAGE = Advice(
    "resolve",
    "An HDRI on the timeline is the stitched panorama image.",
    "The timeline should carry the shooter's HDRI video clip instead, so the stringout shows it. The "
    "stitched panorama is delivered by the shooters separately.",
)
"""Not a QC rule: an HDRI row (QC-080) whose clip is an EXR (memory: the HDRI on the
timeline is the shooter's video clip, 2026-09-29)."""

NO_PLATE = Advice(
    "look",
    "A shot has reference clips but no plate.",
    "Please check the Shot is typed right on these clips: a typo sends a clip to a shot that does not "
    "exist. Fine if this shot really has no plate in this turnover.",
)
"""Not a QC rule: turnover134's mirror ball typed SECA0001 for SECA0011 (2026-10-06)."""

KIND_WORDS = {
    "pl": "plate",
    "cp": "clean plate",
    "el": "element",
    "wit": "witness",
    "re": "reference",
    "colorChart": "colour chart",
    "greyBall": "grey ball",
    "mirrorBall": "mirror ball",
    "sizeRef": "size reference",
}


class Clip(NamedTuple):
    """One line under an item: who it is, the file, and what is particular to it."""

    who: str = ""
    name: str = ""
    detail: str = ""


@dataclass
class Item:
    """One thing to fix, and every clip it applies to."""

    advice: Advice
    blocks: bool = False
    clips: list[Clip] = field(default_factory=list)


@dataclass
class TurnoverReport:
    turnover: Turnover
    clips: int
    blocked: int
    items: list[Item]


def report_name(batch: Batch, when: date | None = None) -> str:
    """`fixit_report_<batch>_<YYYYMMDD>.html`, beside the two spreadsheets (NAMING_SPEC section 5)."""
    return f"fixit_report_{batch.name}_{(when or date.today()):%Y%m%d}.html"


def report_path(batch: Batch, delivery_root: Path, when: date | None = None) -> Path:
    """Beside the two spreadsheets, under `<delivery_root>/<show>/_reports/`."""
    qc_log, _ = exports.report_paths(batch, delivery_root, when)
    return qc_log.parent / report_name(batch, when)


def write(batch: Batch, path: Path, when: date | None = None) -> Path:
    """Write the page, through a temporary name so a half-written page is never left."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".part")
    partial.write_text(render(batch, when), encoding="utf-8")
    partial.replace(path)
    return path


def reports(batch: Batch) -> list[TurnoverReport]:
    """Each turnover's items, in the order the page shows them."""
    return [_turnover_report(batch, turnover) for turnover in batch.turnovers]


def _turnover_report(batch: Batch, turnover: Turnover) -> TurnoverReport:
    rows = [row for row in batch.rows if row.turnover_id == turnover.turnover_id]
    delivered = [row for row in rows if not qc.is_shooter_delivered(row)]
    items: dict[str, Item] = {}
    any_amf_finding = any(r.rule_id == "QC-075" for row in rows for r in row.qc)
    for result in turnover.qc:
        if result.rule_id not in ADVICE or (result.rule_id == "QC-008" and any_amf_finding):
            continue  # not Ben's, or QC-075 already lists the same clips one by one
        _add(items, result.rule_id, ADVICE[result.rule_id], result, _turnover_clips(result, delivered))
    for row in rows:
        if qc.is_shooter_delivered(row) and row.clip_name.lower().endswith(".exr"):
            _add(items, "HDRI", HDRI_IMAGE, None, [Clip(name=row.clip_name)])
    blocked = 0
    for row in delivered:
        row_blocks = False
        for result in row.qc:
            if result.rule_id in ADVICE:
                _add(items, result.rule_id, ADVICE[result.rule_id], result, [_clip(row, result)])
                row_blocks |= result.severity == "error"
        blocked += row_blocks
    if orphans := _without_a_plate(delivered):
        _add(items, "NO_PLATE", NO_PLATE, None, orphans)
    for item in items.values():
        if len(delivered) > 1 and _every_clip(item, delivered):
            item.clips = [Clip(detail=f"Every clip in this turnover ({len(delivered)}).")]
    order = list(SECTIONS)
    ranked = sorted(items.items(), key=lambda kv: (order.index(kv[1].advice.where), not kv[1].blocks, kv[0]))
    return TurnoverReport(turnover, len(delivered), blocked, [item for _, item in ranked])


def _every_clip(item: Item, rows: list[ShotRow]) -> bool:
    """A long list that says nothing a count would not: each clip, none with a detail."""
    names = {clip.name for clip in item.clips if not clip.detail}
    return len(item.clips) == len(names) and names == {row.clip_name for row in rows}


def _add(
    items: dict[str, Item], key: str, advice: Advice, result: QCResult | None, clips: list[Clip]
) -> None:
    item = items.setdefault(key, Item(advice))
    if result is not None and result.severity == "error":
        item.blocks = True
    item.clips.extend(clip for clip in clips if clip not in item.clips)


def _turnover_clips(result: QCResult, rows: list[ShotRow]) -> list[Clip]:
    """QC-064 names its clips after a colon; a clip also on a row of its own is a
    duplicate row (turnover135's C026_S003). Other turnover rules name no clip."""
    if result.rule_id == "QC-064":
        named = {row.clip_name for row in rows}
        names = [name.strip() for name in result.message.split(": ", 1)[-1].split(",") if name.strip()]
        return [Clip(name=name, detail=DUPLICATE_ROW if name in named else "") for name in names]
    if ADVICE[result.rule_id].detail == "message":
        return [Clip(detail=_plain(result.message))]
    return []


DUPLICATE_ROW = "it is also on another row that has a Shot Type, so this blank row can go"


def _without_a_plate(rows: list[ShotRow]) -> list[Clip]:
    """The clips of every shot that has reference clips and no plate in this turnover."""
    plated = {row.shot_code for row in rows if row.identity and row.identity.kind == "pl"}
    return [Clip(_who(row), row.clip_name) for row in rows if row.shot_code and row.shot_code not in plated]


def _clip(row: ShotRow, result: QCResult) -> Clip:
    """`SECA0012 plate`, its file, then what is particular to this clip."""
    return Clip(_who(row), row.clip_name, _detail(row, result))


def _who(row: ShotRow) -> str:
    identity = row.identity
    if identity is None:
        return row.shot_code or ""
    word = KIND_WORDS.get(identity.kind, identity.kind)
    number = "" if identity.index in ("", "01", "1") else f" {int(identity.index)}"
    return f"{row.shot_code} {word}{number}"


def _detail(row: ShotRow, result: QCResult) -> str:
    kind = ADVICE[result.rule_id].detail
    if kind == "message":
        return _plain(result.message)
    if kind == "range":
        return _range_detail(row)
    if kind == "handles":
        return _handles_detail(result.message)
    return ""


def _plain(message: str) -> str:
    return message.removeprefix(models.FIX_IN_RESOLVE)


def _range_detail(row: ShotRow) -> str:
    """How far the EDL's cut falls outside the file, in seconds."""
    if row.media is None or row.approved is None:
        return ""
    fps = row.media.rate.as_float()
    before = row.media.start_frame - row.approved.in_frame
    after = row.approved.out_frame - row.media.max_available_out
    if before > 0:
        return f"the cut starts {_seconds(before, fps)} before the file does"
    if after > 0:
        return f"the cut ends {_seconds(after, fps)} after the file does"
    return ""


def _seconds(frames: int, fps: float) -> str:
    if frames < fps:
        return f"{frames} frame{'s' if frames != 1 else ''}"
    seconds = round(frames / fps)
    return f"about {seconds} second{'s' if seconds != 1 else ''}"


_SHORT = re.compile(r"(\d+) (before In|after Out)")


def _handles_detail(message: str) -> str:
    sides = {"before In": "before the cut", "after Out": "after the cut"}
    return " and ".join(_spare(int(count)) + " " + sides[side] for count, side in _SHORT.findall(message))


def _spare(count: int) -> str:
    return "no spare frames" if count == 0 else f"only {count} spare frame{'s' if count != 1 else ''}"


# --- the page -------------------------------------------------------------------------


def render(batch: Batch, when: date | None = None) -> str:
    """The whole page."""
    day = when or date.today()
    found = reports(batch)
    body = "".join(_turnover_html(report) for report in found)
    names = [_turnover_name(report.turnover) for report in found]
    title = "Fix-it report"
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{title}</title><style>{_STYLE}</style></head><body><main>"
        f'<header><div class="eyebrow">{_e(", ".join(names))}</div><h1>{title}</h1>'
        '<p class="lede">What needs changing before ProIngest can deliver '
        f"{'this turnover' if len(found) == 1 else 'these turnovers'}. Anything that stops a clip "
        "from being delivered comes first in each list.</p>"
        f"{_summary(found)}</header>{body}"
        f"<footer>Made by ProIngest {__version__} on {day.day} {day:%B %Y}. When these are fixed, "
        "export the EDL, metadata CSV and AMFs again into the same folder, and the editor can "
        "re-scan the turnover.</footer></main></body></html>"
    )


def _turnover_name(turnover: Turnover) -> str:
    if turnover.number is None:
        return turnover.folder.name
    return f"Turnover {turnover.number}"


def _status(report: TurnoverReport) -> str:
    if report.blocked == 0:
        return "Nothing blocking"
    if report.blocked >= report.clips:
        return "Every clip blocked"
    return f"{report.blocked} of {report.clips} clips blocked"


def _summary(found: list[TurnoverReport]) -> str:
    if len(found) < 2:
        return ""
    lines = ""
    for r in found:
        name, marker = _e(_turnover_name(r.turnover)), "blocks" if r.blocked else "ok"
        lines += (
            f'<li class="{"resolve" if r.blocked else "note"}"><span class="name">{name}</span>'
            f'<span class="{marker}">{_status(r)}</span></li>'
        )
    return f'<ol class="summary">{lines}</ol>'


def _turnover_html(report: TurnoverReport) -> str:
    turnover = report.turnover
    head = (
        f'<section class="turnover"><h2>{_e(_turnover_name(turnover))}</h2>'
        f'<p class="folder-name"><code>{_e(turnover.folder.name)}</code> &middot; '
        f'<span class="{"blocks" if report.blocked else "ok"}">{_status(report)}</span></p>'
    )
    if not report.items:
        return head + f'<p class="clean">{NOTHING_TO_FIX}</p></section>'
    groups = ""
    for where, heading in SECTIONS.items():
        items = [item for item in report.items if item.advice.where == where]
        if items:
            groups += f"<h3>{heading}</h3><ol>{''.join(_item_html(item) for item in items)}</ol>"
    return head + groups + "</section>"


NOTHING_TO_FIX = "Nothing to fix. Every clip in this turnover is ready to deliver."

_CLASSES: dict[Where, str] = {"resolve": "resolve", "folder": "folder", "look": "note"}
_TAGS: dict[Where, str] = {
    "resolve": "Fix in Resolve -",
    "folder": "Fix in the folder -",
    "look": "Worth a look -",
}


def _item_html(item: Item) -> str:
    advice = item.advice
    clips = "".join(f"<li>{_clip_html(clip)}</li>" for clip in item.clips)
    listed = f'<ul class="clips">{clips}</ul>' if clips else ""
    effect = (
        '<p class="blocks">Stops these clips from being delivered.</p>'
        if item.blocks
        else '<p class="ok">Does not stop the delivery.</p>'
    )
    return (
        f'<li class="{_CLASSES[advice.where]}"><p><span class="tag">{_TAGS[advice.where]}</span> '
        f'<span class="what">{_e(advice.title)}</span></p><p>{_e(advice.explain)}</p>{listed}{effect}</li>'
    )


def _clip_html(clip: Clip) -> str:
    """Who in prose, the file in code type, the detail after it."""
    parts = []
    if clip.who:
        parts.append(_e(clip.who) + (":" if clip.name else ""))
    if clip.name:
        parts.append(f"<code>{_e(clip.name)}</code>")
    if clip.detail:
        parts.append(f"({_e(clip.detail)})" if parts else _e(clip.detail))
    return " ".join(parts)


def _e(text: str) -> str:
    return html.escape(text, quote=True)


_STYLE = """
:root{--bg:#f6f7f9;--card:#fff;--fg:#1d2128;--muted:#5d6573;--line:#dfe3e8;--resolve:#b4231b;
--folder:#8a5a00;--note:#2f5e9e;--sans:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;
--mono:ui-monospace,Menlo,Consolas,monospace}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#15181d;--card:#1d2127;
--fg:#e4e7ec;--muted:#9aa3b0;--line:#2c323a;--resolve:#ff8a80;--folder:#f0c060;--note:#8db8f0;
color-scheme:dark}}
:root[data-theme="dark"]{--bg:#15181d;--card:#1d2127;--fg:#e4e7ec;--muted:#9aa3b0;--line:#2c323a;
--resolve:#ff8a80;--folder:#f0c060;--note:#8db8f0;color-scheme:dark}
body{margin:0;background:var(--bg);color:var(--fg);font-family:var(--sans);font-size:16px;line-height:1.55;
padding:32px 16px 48px}
main{max-width:720px;margin:0 auto;display:grid;gap:28px}
header{display:grid;gap:8px}
.eyebrow{font-family:var(--mono);font-size:13px;color:var(--muted)}
h1{font-size:28px;line-height:1.2;margin:0}
h2{font-size:22px;margin:0}
h3{font-size:14px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:16px 0 0}
.lede,.folder-name{color:var(--muted);margin:0}
section.turnover{display:grid;gap:12px;border-top:1px solid var(--line);padding-top:20px}
ol{list-style:none;margin:0;padding:0;display:grid;gap:12px}
ol>li{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--line);border-radius:6px;
padding:14px 16px;display:grid;gap:6px;min-width:0}
li.resolve{border-left-color:var(--resolve)} li.folder{border-left-color:var(--folder)}
li.note{border-left-color:var(--note)}
.tag{font-weight:700} .resolve .tag{color:var(--resolve)} .folder .tag{color:var(--folder)}
.note .tag{color:var(--note)}
.what{font-weight:600}
li p{margin:0}
ul.clips{margin:0;padding-left:20px;font-size:15px}
.blocks{font-size:13px;font-weight:600;color:var(--resolve)}
.ok{font-size:13px;color:var(--muted)}
.clean{margin:0}
.summary li{display:flex;flex-wrap:wrap;gap:4px 12px;align-items:baseline;padding:10px 14px}
.name{font-weight:700}
code{font-family:var(--mono);font-size:13.5px;background:var(--bg);border:1px solid var(--line);
border-radius:3px;padding:0 4px;overflow-wrap:anywhere}
footer{color:var(--muted);font-size:14px;border-top:1px solid var(--line);padding-top:16px}
"""
