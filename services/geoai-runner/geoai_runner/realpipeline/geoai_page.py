"""Render the interactive GeoAI showcase page from pipeline outputs.

Self-contained HTML (previews embedded as base64) so it works from ``file://``
or a localhost static server and can be committed and screenshotted. The page
is generated from the component registry + the run manifest, so it never drifts
from what actually ran.
"""

from __future__ import annotations

import base64
import html
from pathlib import Path

import pandas as pd

from geoai_runner.realpipeline.registry import COMPONENTS, GeoAIComponent

# Which preview images illustrate each component (input -> AI output).
PREVIEWS: dict[str, list[tuple[str, str]]] = {
    "sar_flood": [
        ("scene_sar_post_vh.png", "Input: Sentinel-1 VH backscatter (dB)"),
        ("A_sar_flood_probability.png", "AI output: flood probability"),
        ("A_sar_flood_binary.png", "AI output: binary flood extent"),
    ],
    "water_unet": [
        ("scene_s2_rgb.png", "Input: Sentinel-2 RGB composite"),
        ("B_water_mask.png", "AI output: U-Net water mask"),
        ("B_water_confidence.png", "AI output: per-pixel confidence"),
    ],
    "susceptibility": [
        ("scene_dem.png", "Input: DEM / terrain"),
        ("C_susceptibility.png", "AI output: susceptibility 0-100"),
    ],
    "infrastructure": [
        ("scene_s2_rgb.png", "Input: Sentinel-2 optical"),
        ("D_buildings.png", "AI output: footprints (red = flood-exposed)"),
    ],
    "embeddings": [
        ("F_fewshot_prediction.png", "AI output: few-shot flood prediction"),
        ("scene_flood_reference.png", "Reference: ground-truth flood"),
    ],
}


def _img_data_uri(path: Path) -> str:
    if not path.exists():
        return ""
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


def _metric_chips(metrics: dict) -> str:
    keys = [
        ("iou", "IoU"),
        ("f1_dice", "F1"),
        ("precision", "Precision"),
        ("recall", "Recall"),
        ("auc", "AUC"),
        ("building_count", "Buildings"),
        ("exposed_count", "Exposed"),
        ("n_training_labels", "Labels"),
        ("n_training_tiles", "Tiles"),
        ("epochs", "Epochs"),
    ]
    chips = []
    for k, label in keys:
        if k in metrics and metrics[k] not in ("", None):
            chips.append(f'<span class="chip"><b>{label}</b> {metrics[k]}</span>')
    return "".join(chips)


def _status_badge(status: str) -> str:
    text = {
        "runnable": "RAN IN THIS BUILD",
        "runnable-fallback": "RAN (OFFLINE FALLBACK)",
        "documented": "ROADMAP / DOCUMENTED",
    }.get(status, status.upper())
    cls = {"runnable": "ok", "runnable-fallback": "warn", "documented": "muted"}.get(
        status, "muted"
    )
    return f'<span class="badge {cls}">{text}</span>'


def _data_mode_badge(metrics: dict) -> str:
    mode = str(metrics.get("data_mode", ""))
    if mode.startswith("real"):
        return '<span class="badge real">REAL DATA</span>'
    if mode.startswith("synthetic"):
        return '<span class="badge muted">SYNTHETIC SCENE</span>'
    return ""


def _component_card(c: GeoAIComponent, metrics: dict, prev_dir: Path, timing) -> str:
    imgs = ""
    for fname, caption in PREVIEWS.get(c.key, []):
        uri = _img_data_uri(prev_dir / fname)
        if uri:
            imgs += (
                f'<figure><img src="{uri}" alt="{html.escape(caption)}"/>'
                f"<figcaption>{html.escape(caption)}</figcaption></figure>"
            )
    runtime = (
        f'<span class="chip"><b>Runtime</b> {timing}s</span>' if timing not in ("", None) else ""
    )
    return f"""
    <article class="card" id="component-{c.letter.lower()}">
      <header class="card-head">
        <div class="letter">{html.escape(c.letter)}</div>
        <div>
          <h3>{html.escape(c.name)} {_status_badge(c.status)}{_data_mode_badge(metrics)}</h3>
          <p class="task">{html.escape(c.ai_task)} &middot; <span class="tier tier-{c.tier.lower()}">{c.tier}</span>
             &middot; <span class="ref">{html.escape(c.book_ref)}</span></p>
        </div>
      </header>
      <p class="plain">{html.escape(c.plain_language)}</p>
      <div class="gallery">{imgs}</div>
      <div class="chips">{_metric_chips(metrics)}{runtime}</div>
      <details><summary>Architecture, data &amp; limitations</summary>
        <dl>
          <dt>Model</dt><dd>{html.escape(c.architecture)}</dd>
          <dt>Inputs</dt><dd>{html.escape(c.inputs)}</dd>
          <dt>Output</dt><dd><code>{html.escape(c.output_artifact)}</code></dd>
          <dt>Feeds into</dt><dd>{html.escape(c.feeds_into)}</dd>
          <dt>Judging criteria</dt><dd>{html.escape(", ".join(c.criteria))}</dd>
          <dt>Limitations</dt><dd>{html.escape(c.limitations)}</dd>
        </dl>
      </details>
    </article>
    """


def _priority_table(scored: pd.DataFrame) -> str:
    cols = [
        ("subdistrict_name", "Subdistrict"),
        ("flood_likelihood_0_100", "Flood likelihood (AI)"),
        ("exposure_0_100", "Exposure (AI)"),
        ("fpps_0_100", "FPPS"),
        ("action_class", "Action"),
        ("confidence_class", "Confidence"),
        ("top_reason", "Top reason"),
    ]
    head = "".join(f"<th>{html.escape(label)}</th>" for _, label in cols)
    rows = ""
    for _, r in scored.iterrows():
        cells = ""
        for key, _ in cols:
            val = r.get(key, "")
            cls = ""
            if key == "action_class":
                cls = f' class="action action-{html.escape(str(val))}"'
            cells += f"<td{cls}>{html.escape(str(val))}</td>"
        rows += f"<tr>{cells}</tr>"
    return f'<table class="priority"><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>'


def write_geoai_page(
    output_path: str | Path,
    manifest: dict,
    scored: pd.DataFrame,
    prev_dir: str | Path,
) -> Path:
    output_path = Path(output_path)
    prev_dir = Path(prev_dir)
    metrics = manifest.get("metrics", {})
    timings = manifest.get("timings_seconds", {})

    cards = "".join(
        _component_card(c, metrics.get(c.key, {}), prev_dir, timings.get(c.key, ""))
        for c in COMPONENTS
    )

    sources = manifest.get("sources") or {}
    sources_html = ""
    if sources:
        items = "".join(
            f"<div><b>{html.escape(k.replace('_', ' ').title())}</b> &nbsp;{html.escape(str(v))}</div>"
            for k, v in sources.items()
        )
        sources_html = f"""
<section class="wrap">
  <h2>Data sources (real)</h2>
  <p class="section-note">Every layer below is fetched live from an authoritative
  source at run time &mdash; no synthetic pixels.</p>
  <div class="sources">{items}</div>
</section>"""

    models_uri = _img_data_uri(prev_dir / "annotated_models.png")
    bridge_uri = _img_data_uri(prev_dir / "annotated_decision_bridge.png")
    overview = ""
    if models_uri or bridge_uri:
        blocks = ""
        if models_uri:
            blocks += f'<figure class="overview-fig"><img src="{models_uri}" alt="AI behind each layer"/></figure>'
        if bridge_uri:
            blocks += f'<figure class="overview-fig"><img src="{bridge_uri}" alt="Decision bridge"/></figure>'
        overview = f"""
<section class="wrap">
  <h2>Annotated overview</h2>
  <p class="section-note">Two explainer graphics, generated by the same run: the AI
  model behind each map layer, and how those layers become a sub-district action list.</p>
  <div class="overview">{blocks}</div>
</section>"""

    a = metrics.get("sar_flood", {})
    b = metrics.get("water_unet", {})
    c = metrics.get("susceptibility", {})
    is_real = str(manifest.get("data_mode", "")).startswith("real")
    if a.get("iou") is not None:
        a_head = f"SAR change detection IoU <b>{a.get('iou')}</b> / F1 <b>{a.get('f1_dice')}</b>"
    else:
        a_head = (
            f"SAR flood extent <b>{float(a.get('flood_fraction', 0)) * 100:.2f}%</b> of district"
        )
    headline = (
        f"{a_head} &nbsp;&bull;&nbsp; U-Net water IoU <b>{b.get('iou', 'n/a')}</b>"
        f" &nbsp;&bull;&nbsp; Susceptibility AUC <b>{c.get('auc', 'n/a')}</b>"
    )
    flood_frac = manifest.get("scene", {}).get("flood_fraction", "")
    if is_real:
        lede = (
            "Six GeoAI components turn <b>real satellite imagery</b> into a sub-district "
            "Flood Preparedness Priority Score. Every model below <b>ran on real data</b> over "
            "Mae Sai, Chiang Rai &mdash; real Sentinel-1 and Sentinel-2, real Copernicus DEM, "
            "real DOPA/DWR boundaries and rivers, real OpenStreetMap buildings."
        )
        notice = (
            "Real data &middot; not an official flood warning &middot; "
            f"SAR flood extent {flood_frac}"
        )
    else:
        lede = (
            "Six GeoAI components turn satellite imagery into a subdistrict Flood "
            "Preparedness Priority Score. Every model below <b>ran in this build</b> on a "
            "coherent synthetic Mae Sai-like scene (real algorithms, real raster I/O, real "
            "PyTorch training)."
        )
        notice = (
            "Synthetic demo scene &middot; not an official flood warning &middot; "
            f"flood fraction {flood_frac}"
        )

    html_doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>FloodGuard - GeoAI Pipeline</title>
<style>{_CSS}</style></head>
<body>
<header class="hero">
  <div class="wrap">
    <p class="kicker">FloodGuard Thailand &middot; GeoAI methodology</p>
    <h1>The AI behind the flood decision layer</h1>
    <p class="lede">{lede}</p>
    <p class="headline">{headline}</p>
    <div class="notice">{notice}</div>
  </div>
</header>
{sources_html}
{overview}
<section class="wrap flow-sec">
  <h2>Pipeline at a glance</h2>
  <div class="flow">
    <div class="fnode">Sentinel-1 SAR<br/><small>all-weather</small></div>
    <div class="arrow">&rarr;</div>
    <div class="fnode ai">A &middot; Change detection<br/><small>flood extent</small></div>
    <div class="arrow">&rarr;</div>
    <div class="fnode ai">B &middot; U-Net refine<br/><small>water mask</small></div>
    <div class="arrow">&rarr;</div>
    <div class="fnode ai">C &middot; Susceptibility<br/><small>where water goes</small></div>
    <div class="arrow">&rarr;</div>
    <div class="fnode ai">D &middot; Buildings<br/><small>who is exposed</small></div>
    <div class="arrow">&rarr;</div>
    <div class="fnode out">Priority score<br/><small>action A-E</small></div>
  </div>
</section>

<section class="wrap">
  <h2>Decision bridge &mdash; AI drives 55% of the priority score</h2>
  <p class="section-note">The two highest-weighted Flood Preparedness Priority Score
  inputs &mdash; <b>flood likelihood (0.30)</b> and <b>exposure (0.25)</b> &mdash; are
  computed by the AI pipeline via zonal statistics over each subdistrict.
  Confidence is set from the agreement between two independent AI signals
  (SAR change and terrain susceptibility).</p>
  {_priority_table(scored)}
</section>

<section class="wrap">
  <h2>The models</h2>
  <div class="cards">{cards}</div>
</section>

<footer class="wrap foot">
  <p>Anchor: Qiusheng Wu, <i>Introduction to GeoAI</i> (2026). Components map to
  Chapters 9, 12, 13, 14, 16. Generated by <code>scripts/run_geoai_pipeline.py</code>.</p>
  <p>FloodGuard is a preparedness and rapid post-event prioritization tool, not an
  official emergency warning system.</p>
</footer>
</body></html>"""
    output_path.write_text(html_doc, encoding="utf-8")
    return output_path


_CSS = """
:root{--bg:#0b1220;--panel:#121b2e;--ink:#e8eef7;--muted:#93a4bd;--line:#243449;
--accent:#3b82f6;--ok:#10b981;--warn:#f59e0b;--water:#38bdf8;}
@media (prefers-color-scheme: light){:root{--bg:#f5f7fb;--panel:#ffffff;--ink:#0f1b2d;
--muted:#5a6b83;--line:#e2e8f0;}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;line-height:1.55}
.wrap{max-width:1080px;margin:0 auto;padding:0 20px}
.hero{background:linear-gradient(135deg,#0e1a33,#132447 60%,#0b2a3f);
color:#eaf1fb;padding:54px 0 40px;border-bottom:1px solid var(--line)}
.kicker{letter-spacing:.14em;text-transform:uppercase;font-size:12px;color:#9fc0ff;margin:0 0 6px}
.hero h1{margin:0 0 12px;font-size:38px;line-height:1.1}
.lede{max-width:760px;color:#cfe0f7;font-size:17px}
.headline{margin-top:14px;font-size:16px;color:#eaf1fb}
.notice{margin-top:16px;display:inline-block;background:rgba(245,158,11,.14);
border:1px solid rgba(245,158,11,.4);color:#ffd699;padding:6px 12px;border-radius:999px;font-size:13px}
h2{margin:38px 0 6px;font-size:24px}
.section-note,.foot p{color:var(--muted)}
.flow-sec{padding-bottom:6px}
.flow{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:14px}
.fnode{background:var(--panel);border:1px solid var(--line);border-radius:12px;
padding:12px 14px;font-weight:600;font-size:14px;text-align:center;min-width:120px}
.fnode small{color:var(--muted);font-weight:400}
.fnode.ai{border-color:var(--accent);box-shadow:0 0 0 1px rgba(59,130,246,.25) inset}
.fnode.out{border-color:var(--ok);box-shadow:0 0 0 1px rgba(16,185,129,.25) inset}
.arrow{color:var(--muted);font-size:20px}
.overview{display:grid;gap:16px;margin-top:14px}
.overview-fig{margin:0;background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:10px;overflow-x:auto}
.overview-fig img{width:100%;min-width:640px;border-radius:8px;display:block}
.cards{display:grid;gap:20px;margin-top:16px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:20px}
.card-head{display:flex;gap:14px;align-items:flex-start}
.letter{width:40px;height:40px;flex:0 0 40px;border-radius:10px;background:var(--accent);
color:#fff;font-weight:800;font-size:20px;display:grid;place-items:center}
.card h3{margin:0;font-size:19px}
.task{margin:2px 0 0;color:var(--muted);font-size:13px}
.tier{font-weight:700}.tier-mvp{color:var(--ok)}.tier-roadmap{color:var(--warn)}.tier-baseline{color:var(--muted)}
.ref{color:var(--muted)}
.plain{margin:12px 0}
.gallery{display:flex;gap:12px;flex-wrap:wrap;margin:8px 0}
.gallery figure{margin:0;flex:1 1 180px;max-width:240px}
.gallery img{width:100%;border-radius:10px;border:1px solid var(--line);display:block;background:#000}
.gallery figcaption{font-size:12px;color:var(--muted);margin-top:5px;text-align:center}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}
.chip{background:rgba(59,130,246,.12);border:1px solid var(--line);border-radius:8px;
padding:3px 9px;font-size:13px}
.badge{font-size:10.5px;font-weight:800;letter-spacing:.04em;padding:2px 8px;border-radius:999px;
vertical-align:middle;margin-left:6px}
.badge.ok{background:rgba(16,185,129,.16);color:#34d399;border:1px solid rgba(16,185,129,.4)}
.badge.warn{background:rgba(245,158,11,.16);color:#fbbf24;border:1px solid rgba(245,158,11,.4)}
.badge.muted{background:rgba(148,164,189,.14);color:var(--muted);border:1px solid var(--line)}
.badge.real{background:rgba(56,189,248,.18);color:#38bdf8;border:1px solid rgba(56,189,248,.45)}
.sources{display:grid;gap:6px;margin-top:12px;font-size:13.5px}
.sources div{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:7px 11px}
.sources b{color:var(--accent)}
details{margin-top:10px;border-top:1px solid var(--line);padding-top:10px}
summary{cursor:pointer;color:var(--accent);font-weight:600;font-size:14px}
dl{display:grid;grid-template-columns:130px 1fr;gap:6px 14px;margin:12px 0 0;font-size:14px}
dt{color:var(--muted)}dd{margin:0}
code{background:rgba(148,164,189,.16);padding:1px 6px;border-radius:5px;font-size:12.5px}
table.priority{width:100%;border-collapse:collapse;margin-top:14px;font-size:14px}
.priority th,.priority td{border-bottom:1px solid var(--line);padding:9px 10px;text-align:left}
.priority th{color:var(--muted);font-weight:600;font-size:12.5px;text-transform:uppercase;letter-spacing:.03em}
.action{font-weight:800;text-align:center}
.action-A{color:#ef4444}.action-B{color:#f59e0b}.action-C{color:#eab308}
.action-D{color:#10b981}.action-E{color:var(--muted)}
.foot{margin:40px auto;padding-top:20px;border-top:1px solid var(--line);font-size:13px}
"""
