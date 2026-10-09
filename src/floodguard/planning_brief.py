"""A one-page Thai and English brief of a published planning result, for printing.

The brief is made from the published result file of a case and from nothing else: every score, class and count on
it is a value of that file. It always carries the source time, the confidence of each row, the assumptions and the
sentence that it is planning guidance and not an official warning. The Thai text was written by the project's
assistant and was not reviewed by a native speaker; the brief says so.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import html
from typing import Any

CLASS_NAMES: dict[str, tuple[str, str]] = {
    "A": ("Protect lives now", "ปกป้องชีวิตทันที"),
    "B": ("Keep routes open", "รักษาเส้นทางให้ใช้งานได้"),
    "C": ("Protect essential services", "คุ้มครองบริการจำเป็น"),
    "D": ("Build resilience", "เสริมความยืดหยุ่น"),
    "E": ("Monitor and verify", "ติดตามและตรวจสอบ"),
}
"""The class names the map of the site shows (``apps/web/src/components/geo-map.tsx``)."""

CLASS_ASKS: dict[str, tuple[str, str]] = {
    "A": ("Review assistance, transport, shelter and medical continuity with the responsible authorities.",
          "ทบทวนความช่วยเหลือ การเดินทาง ศูนย์พักพิง และความต่อเนื่องทางการแพทย์กับหน่วยงานที่รับผิดชอบ"),
    "B": ("Look first at the roads whose closure cuts residents off, and plan to keep them passable.",
          "ตรวจสอบถนนที่เมื่อปิดแล้วทำให้ผู้อยู่อาศัยถูกตัดขาดเป็นอันดับแรก และวางแผนให้สัญจรได้"),
    "C": ("Check that hospitals and shelters stay reachable.", "ตรวจสอบว่าโรงพยาบาลและศูนย์พักพิงยังเข้าถึงได้"),
    "D": ("No urgent trigger in this scenario. Plan drainage, routes and shelters before the season.",
          "ไม่มีเงื่อนไขเร่งด่วนในสถานการณ์จำลองนี้ วางแผนระบบระบายน้ำ เส้นทาง และศูนย์พักพิงก่อนถึงฤดูฝน"),
    "E": ("Lower relative priority in this scenario. Keep watching and check on the ground.",
          "ลำดับความสำคัญต่ำกว่าเมื่อเทียบกันในสถานการณ์จำลองนี้ เฝ้าติดตามและตรวจสอบในพื้นที่"),
}
CONFIDENCE_TH = {"low": "ต่ำ", "medium": "ปานกลาง", "high": "สูง"}
STATUS = ("Planning guidance. Not an official warning. A scenario of the 2024 flood season, not the flood of any single day.",
          "ข้อมูลประกอบการวางแผน ไม่ใช่คำเตือนอย่างเป็นทางการ เป็นสถานการณ์จำลองจากฤดูน้ำท่วม พ.ศ. 2567 ไม่ใช่น้ำท่วมของวันใดวันหนึ่ง")
OFFICIAL = ("In an emergency follow the announcements of the DDPM and the Thai Meteorological Department.",
            "ในเหตุฉุกเฉินโปรดปฏิบัติตามประกาศของกรมป้องกันและบรรเทาสาธารณภัย (ปภ.) และกรมอุตุนิยมวิทยา")
NEVER_SAFE = ("Class E never means safe. It means lower relative priority in this scenario.",
              "ระดับ E ไม่ได้หมายความว่าปลอดภัย หมายถึงลำดับความสำคัญต่ำกว่าเมื่อเทียบกันในสถานการณ์จำลองนี้")
ASSUMPTIONS: tuple[tuple[str, str], ...] = (
    ("Road closures are modelled from the flood layer. No closure was observed.",
     "การปิดถนนเป็นการจำลองจากชั้นข้อมูลน้ำท่วม ไม่ใช่การปิดถนนที่สังเกตได้จริง"),
    ("Residents are modelled counts (WorldPop 2020).", "จำนวนผู้อยู่อาศัยเป็นค่าจากแบบจำลอง (WorldPop 2020)"),
    ("The flood layer is an agency product that was not checked in the field.",
     "ชั้นข้อมูลน้ำท่วมเป็นผลิตภัณฑ์ของหน่วยงาน ยังไม่ได้ตรวจสอบภาคสนาม"),
)
STABILITY_NOT_EVALUATED = ("How stable each class is under other assumptions: not evaluated in the published result.",
                           "ความเสถียรของแต่ละระดับภายใต้สมมติฐานอื่น: ยังไม่ได้ประเมินในผลที่เผยแพร่")
THAI_NOTE = ("Thai text written by the project's assistant; not reviewed by a native speaker.",
             "ข้อความภาษาไทยเขียนโดยผู้ช่วยของโครงการ ยังไม่ได้ตรวจทานโดยเจ้าของภาษา")
HEADERS: tuple[tuple[str, str], ...] = (
    ("Tambon", "ตำบล"), ("Score (0 to 100)", "คะแนน FPPS"), ("Class", "ระดับการดำเนินการ"), ("Confidence", "ความเชื่อมั่น"),
    ("Residents", "ผู้อยู่อาศัย"), ("Inside the mapped water", "อยู่ในพื้นที่น้ำท่วมตามแผนที่"),
    ("Lose a hospital within 30 minutes", "เข้าถึงโรงพยาบาลภายใน 30 นาทีไม่ได้"), ("Lose every road route", "ถูกตัดขาดจากทุกเส้นทางถนน"),
)


class PlanningBriefError(ValueError):
    """The published file does not hold what a brief needs."""


def _count(value: Any) -> str:
    return "n/a" if value is None else f"{round(float(value)):,}"


def rows_of(overlay: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The values of the brief for every unit of a published result, highest score first.

    Raises:
        PlanningBriefError: for a file that is not a non-operational planning result, or a row without a class.
    """

    if overlay.get("official_warning") is not False or overlay.get("operational_status") != "non_operational":
        raise PlanningBriefError("a brief is made only from a result that says it is not operational and not an official warning")
    listed = []
    for row in overlay.get("rows") or []:
        letter = row.get("action_class")
        if letter not in CLASS_NAMES:
            raise PlanningBriefError(f"unit {row.get('unit_id')} has no class of A to E")
        parts = row["components"]
        hospital = next((service for service in parts["access_gap_0_100"].get("services", []) if service["service"] == "hospital"), None)
        listed.append({
            "unit_id": row["unit_id"], "name_en": row["unit_name_en"], "name_th": row["unit_name_th"],
            "score": float(row["fpps_0_100"]), "class": letter, "confidence": row["confidence"]["confidence_class"],
            "residents": parts["exposure_0_100"]["inputs"]["unit_residents"],
            "inside": parts["exposure_0_100"]["inputs"]["residents_inside_flood_extent"],
            "lose_hospital": None if hospital is None else hospital["newly_lost_residents"],
            "lose_routes": parts["road_criticality_0_100"]["inputs"]["residents_losing_all_routes"],
            "stability": (row.get("headline_stability") or {}).get("status"),
        })
    if not listed:
        raise PlanningBriefError("the published file holds no row")
    return sorted(listed, key=lambda item: (-item["score"], item["unit_id"]))


def flood_window(overlay: Mapping[str, Any]) -> str:
    """The time the flood input stands for, as the published file states it."""

    for item in overlay.get("inputs") or []:
        if item.get("role") == "flood_input" and item.get("source_timestamp"):
            return str(item["source_timestamp"]).replace("/", " to ")
    return str(overlay["source_timestamp"])


def credits_of(overlay: Mapping[str, Any]) -> list[str]:
    """The attribution of the flood input with its licence and change notice, and the open data beside it."""

    listed = []
    for item in overlay.get("inputs") or []:
        if item.get("role") == "flood_input":
            listed.append(f"{item['attribution']} ({item['licence']}). Changed by FloodGuard; this brief holds values derived from the layer, "
                          f"shared under {item['licence']}.")
    listed.append("Roads © OpenStreetMap contributors (ODbL 1.0). Residents: WorldPop 2020 (CC BY 4.0). Boundaries: HDX Thailand COD-AB.")
    return listed


def _table(rows: Sequence[Mapping[str, Any]]) -> tuple[list[str], list[list[str]]]:
    header = [f"{english} / {thai}" for english, thai in HEADERS]
    body = [[f"{row['name_en']} / {row['name_th']}", f"{row['score']:.1f}",
             f"{row['class']}: {CLASS_NAMES[row['class']][0]} / {CLASS_NAMES[row['class']][1]}",
             f"{row['confidence']} / {CONFIDENCE_TH.get(row['confidence'], row['confidence'])}",
             _count(row["residents"]), _count(row["inside"]), _count(row["lose_hospital"]), _count(row["lose_routes"])] for row in rows]
    return header, body


def stability_line(rows: Sequence[Mapping[str, Any]], note: tuple[str, str] | None) -> list[tuple[str, str]]:
    """What the brief says of stability: the status of the published file, and a report-only note when one is given."""

    lines = [STABILITY_NOT_EVALUATED] if all(row["stability"] in (None, "not_evaluated") for row in rows) else []
    if note is not None:
        lines.append(note)
    return lines


def render_markdown(overlay: Mapping[str, Any], *, source_sha256: str, source_path: str, stability_note: tuple[str, str] | None = None) -> str:
    """The brief as Markdown."""

    rows = rows_of(overlay)
    header, body = _table(rows)
    case = overlay["case"]
    lines = [f"# {case['title_en']}", f"## {case['title_th']}", "",
             f"> **{STATUS[0]}**", ">", f"> **{STATUS[1]}**", "",
             f"- Flood layer / ชั้นข้อมูลน้ำท่วม: {flood_window(overlay)}. Result made / จัดทำผลเมื่อ: {overlay['generated_at']}.",
             "- Closure level / ระดับการปิดถนน: central / ระดับกลาง. Class rule / กฎการจัดระดับ: v1.", "",
             "| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(cells) + " |" for cells in body]
    lines += ["", "### What each class asks / แต่ละระดับหมายถึงอะไร", ""]
    lines += [f"- **{letter}: {CLASS_NAMES[letter][0]} / {CLASS_NAMES[letter][1]}.** {CLASS_ASKS[letter][0]} / {CLASS_ASKS[letter][1]}"
              for letter in sorted({row["class"] for row in rows})]
    lines += ["", f"**{NEVER_SAFE[0]}** / **{NEVER_SAFE[1]}**", ""]
    lines += [f"- {english} / {thai}" for english, thai in stability_line(rows, stability_note)]
    lines += ["", "### Assumptions / สมมติฐาน", ""]
    lines += [f"- {english} / {thai}" for english, thai in ASSUMPTIONS]
    lines += ["", f"{OFFICIAL[0]} / {OFFICIAL[1]}", "", "---", ""]
    lines += [f"Credits: {' '.join(credits_of(overlay))}", "",
              f"Made from `{source_path}` (SHA-256 `{source_sha256}`). {THAI_NOTE[0]} / {THAI_NOTE[1]}", ""]
    return "\n".join(lines)


def render_html(overlay: Mapping[str, Any], *, source_sha256: str, source_path: str, stability_note: tuple[str, str] | None = None) -> str:
    """The brief as one self-contained page that prints on one sheet of A4, landscape."""

    rows = rows_of(overlay)
    header, body = _table(rows)
    case = overlay["case"]
    escape = html.escape

    def pair(text: tuple[str, str], tag: str = "p", css: str = "") -> str:
        return f'<{tag}{css}><span lang="en">{escape(text[0])}</span><br><span lang="th">{escape(text[1])}</span></{tag}>'

    head = "".join(f"<th>{escape(cell).replace(' / ', '<br>')}</th>" for cell in header)
    lines = "".join(
        "<tr>" + "".join(f'<td class="{"name" if index in (0, 2) else "number"}">{escape(cell).replace(" / ", "<br>")}</td>'
                         for index, cell in enumerate(cells)) + "</tr>" for cells in body)
    asks = "".join(f"<li><strong>{letter}: {escape(CLASS_NAMES[letter][0])} / {escape(CLASS_NAMES[letter][1])}.</strong> "
                   f"{escape(CLASS_ASKS[letter][0])}<br>{escape(CLASS_ASKS[letter][1])}</li>" for letter in sorted({row["class"] for row in rows}))
    notes = "".join(f"<li>{escape(english)}<br>{escape(thai)}</li>" for english, thai in (*stability_line(rows, stability_note), *ASSUMPTIONS))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(case['title_en'])}</title>
<style>
@page {{ size: A4 landscape; margin: 10mm; }}
body {{ font-family: "Noto Sans Thai", "Sarabun", "Leelawadee UI", Tahoma, Arial, sans-serif; font-size: 9.5pt; line-height: 1.3; color: #111; margin: 0 auto; max-width: 277mm; padding: 4mm; background: #fff; }}
h1 {{ font-size: 14pt; margin: 0; }} h2 {{ font-size: 12pt; margin: 0 0 2mm; font-weight: 600; }} h3 {{ font-size: 10pt; margin: 3mm 0 1mm; }}
.status {{ border: 1.5pt solid #111; padding: 2mm 3mm; margin: 2mm 0; font-weight: 700; }}
.meta, .foot {{ font-size: 8pt; color: #333; }}
table {{ border-collapse: collapse; width: 100%; margin: 2mm 0; }}
th, td {{ border: 0.5pt solid #555; padding: 1mm 1.5mm; vertical-align: top; }}
th {{ background: #eee; font-size: 8pt; text-align: left; }} td.number {{ text-align: right; white-space: nowrap; }}
ul {{ margin: 0; padding-left: 5mm; }} li {{ margin-bottom: 0.8mm; }}
.columns {{ display: grid; grid-template-columns: 1fr 1fr; gap: 5mm; }}
@media (max-width: 800px) {{ .columns {{ grid-template-columns: 1fr; }} table {{ font-size: 8pt; }} }}
</style>
</head>
<body>
<h1>{escape(case['title_en'])}</h1>
<h2 lang="th">{escape(case['title_th'])}</h2>
{pair(STATUS, "div", ' class="status"')}
<p class="meta">Flood layer / ชั้นข้อมูลน้ำท่วม: {escape(flood_window(overlay))}. Result made / จัดทำผลเมื่อ: {escape(str(overlay['generated_at']))}. Closure level / ระดับการปิดถนน: central / ระดับกลาง. Class rule / กฎการจัดระดับ: v1.</p>
<table><thead><tr>{head}</tr></thead><tbody>{lines}</tbody></table>
<div class="columns">
<div><h3>What each class asks / แต่ละระดับหมายถึงอะไร</h3><ul>{asks}</ul>{pair(NEVER_SAFE, "p", ' style="font-weight:700"')}</div>
<div><h3>Stability and assumptions / ความเสถียรและสมมติฐาน</h3><ul>{notes}</ul>{pair(OFFICIAL)}</div>
</div>
<p class="foot">Credits: {escape(' '.join(credits_of(overlay)))}<br>Made from {escape(source_path)} (SHA-256 {escape(source_sha256)}). {escape(THAI_NOTE[0])} / {escape(THAI_NOTE[1])}</p>
</body>
</html>
"""
