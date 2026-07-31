"""Render annotated 'AI behind each layer' + 'decision bridge' figures.

These are the explainer graphics for the proposal and the GeoAI page. They are
generated from the run's own previews and scored table, so they never drift from
what actually ran.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

_INK = "#0f1b2d"
_ACCENT = "#2563eb"
_MUT = "#5a6b83"
_OK = "#0e7a4f"
_ACT = {"A": "#ef4444", "B": "#f59e0b", "C": "#eab308", "D": "#10b981", "E": "#94a3b8"}


def _img(prev_dir: Path, name: str):
    import matplotlib.image as mpimg

    return mpimg.imread(str(prev_dir / name))


def render_annotated_models(prev_dir: Path, metrics: dict, out_path: Path) -> Path:
    """Four-component annotated explainer (input -> AI output -> model + metric)."""

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    m = metrics
    inf = m.get("infrastructure", {})
    is_real = str(m.get("sar_flood", {}).get("data_mode", "")).startswith("real")

    a = m.get("sar_flood", {})
    if a.get("iou") is not None:
        a_metric = f"IoU {a.get('iou')}  ·  F1 {a.get('f1_dice')}"
    else:  # real run: no independent ground-truth mask, so report extent
        a_metric = (
            f"{a.get('flood_fraction', 0) * 100:.2f}% flooded · "
            f"pre {str(a.get('pre_datetime', ''))[:10]} → post {str(a.get('post_datetime', ''))[:10]}"
        )
    b = m.get("water_unet", {})
    b_caption = (
        "A ResNet-U-Net learns the spectral fingerprint of water from 6 Sentinel-2\n"
        "bands, giving smooth water bodies with a per-pixel confidence."
        + (
            "\nEncoder: real ImageNet-pretrained weights."
            if b.get("encoder_weights") == "imagenet"
            else "\nTrained from scratch on CPU (no pretrained weights)."
        )
    )
    d_sub = (
        "Ch. 14 · OpenStreetMap footprints (real)"
        if is_real
        else "Ch. 14 · SAM 3 (offline fallback)"
    )
    d_caption = (
        "Building footprints let us flag structures the flood touches.\n"
        "Red = flood-exposed, black = not exposed. Feeds equity & shelter-demand."
    )
    rows = [
        (
            "A",
            "SAR Flood-Extent Detection",
            "Ch. 12 · Traditional change detection",
            [
                ("scene_sar_post_vh.png", "Sentinel-1 VH (radar)"),
                ("A_sar_flood_probability.png", "AI: flood probability"),
            ],
            "Radar backscatter DROPS where dry ground becomes open water. Pre/post\n"
            "differencing in dB + threshold. All-weather (sees through cloud). No labels.",
            a_metric,
        ),
        (
            "B",
            "Water-Mask Refinement (U-Net)",
            "Ch. 9 · Semantic segmentation",
            [
                ("scene_s2_rgb.png", "Sentinel-2 optical"),
                ("B_water_mask.png", "AI: U-Net water mask"),
            ],
            b_caption,
            f"IoU {b.get('iou', 'n/a')}  ·  F1 {b.get('f1_dice', 'n/a')}",
        ),
        (
            "C",
            "Flood Susceptibility Surface",
            "Ch. 13 · Pixel-level regression",
            [
                ("scene_dem.png", "DEM / terrain"),
                ("C_susceptibility.png", "AI: susceptibility 0-100"),
            ],
            "Terrain tells you where water goes: low ground near rivers floods first\n"
            "(HAND, slope, distance, TWI). Works for sub-districts never analyst-mapped.",
            f"AUC {m.get('susceptibility', {}).get('auc', 'n/a')}"
            + (" vs real SAR flood extent" if is_real else " (flood vs dry separability)"),
        ),
        (
            "D",
            "Critical-Infrastructure Extraction",
            d_sub,
            [
                ("scene_s2_rgb.png", "Optical + built-up"),
                ("D_buildings.png", "AI: exposed footprints"),
            ],
            d_caption,
            f"{inf.get('building_count', 'n/a')} buildings · {inf.get('exposed_count', 'n/a')} flood-exposed",
        ),
    ]

    fig = plt.figure(figsize=(13.5, 15.5), dpi=110)
    fig.patch.set_facecolor("white")
    fig.text(
        0.5,
        0.975,
        "FloodGuard — the AI behind each layer",
        ha="center",
        fontsize=23,
        fontweight="bold",
        color=_INK,
    )
    subtitle = (
        "Anchor: Qiusheng Wu, Introduction to GeoAI (2026). Every model ran end-to-end on "
        + (
            "REAL data over Mae Sai, Chiang Rai (Sentinel-1/2, Copernicus DEM, DOPA/DWR/OSM)."
            if is_real
            else "a coherent synthetic Mae Sai-like scene."
        )
    )
    fig.text(0.5, 0.957, subtitle, ha="center", fontsize=11, color=_MUT)
    gs = fig.add_gridspec(
        4,
        3,
        left=0.04,
        right=0.985,
        top=0.935,
        bottom=0.02,
        hspace=0.28,
        wspace=0.12,
        width_ratios=[1, 1, 1.35],
    )
    for i, (letter, title, sub, imgs, expl, metric) in enumerate(rows):
        axc = fig.add_subplot(gs[i, 2])
        axc.axis("off")
        for j, (fn, cap) in enumerate(imgs):
            ax = fig.add_subplot(gs[i, j])
            ax.imshow(_img(prev_dir, fn))
            ax.axis("off")
            ax.set_title(cap, fontsize=10.5, color=_INK, pad=4)
            if j == 1:
                ax.annotate(
                    "",
                    xy=(-0.10, 0.5),
                    xytext=(-0.02, 0.5),
                    xycoords="axes fraction",
                    arrowprops=dict(arrowstyle="-|>", color=_ACCENT, lw=2.4),
                )
        axc.add_patch(
            FancyBboxPatch(
                (0.02, 0.06),
                0.96,
                0.88,
                transform=axc.transAxes,
                boxstyle="round,pad=0.02,rounding_size=0.04",
                fc="#f4f7fc",
                ec="#d7e0ee",
                lw=1.2,
            )
        )
        axc.text(
            0.07,
            0.86,
            letter,
            transform=axc.transAxes,
            fontsize=25,
            fontweight="bold",
            color="white",
            bbox=dict(boxstyle="round,pad=0.28", fc=_ACCENT, ec="none"),
            va="top",
        )
        axc.text(
            0.24,
            0.90,
            title,
            transform=axc.transAxes,
            fontsize=13.5,
            fontweight="bold",
            color=_INK,
            va="top",
        )
        axc.text(
            0.24,
            0.79,
            sub,
            transform=axc.transAxes,
            fontsize=10.5,
            color=_ACCENT,
            va="top",
            style="italic",
        )
        axc.text(
            0.07,
            0.62,
            expl,
            transform=axc.transAxes,
            fontsize=11,
            color="#25324a",
            va="top",
            linespacing=1.5,
        )
        axc.text(
            0.07,
            0.14,
            "Executed:",
            transform=axc.transAxes,
            fontsize=10.5,
            color=_MUT,
            va="top",
            fontweight="bold",
        )
        axc.text(
            0.28,
            0.14,
            metric,
            transform=axc.transAxes,
            fontsize=11.5,
            color=_OK,
            va="top",
            fontweight="bold",
        )
    footer = (
        "Real Mae Sai data (Planetary Computer + Thai NGIS/DOPA/DWR + OSM) · not an official flood warning"
        if is_real
        else "Synthetic demo scene · not an official flood warning · real tiles are a data swap, not a code change"
    )
    fig.text(0.5, 0.006, footer, ha="center", fontsize=9.5, color=_MUT)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return out_path


def render_decision_bridge(
    prev_dir: Path,
    scored: pd.DataFrame,
    out_path: Path,
    subs: dict | None = None,
    bbox=None,
    is_real: bool = False,
) -> Path:
    """AI rasters -> zonal stats -> subdistrict priority table figure."""

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch, Rectangle

    df = scored.copy()
    fig = plt.figure(figsize=(13.5, 7.6), dpi=110)
    fig.patch.set_facecolor("white")
    fig.text(
        0.5,
        0.955,
        "Decision bridge — AI drives 55% of the priority score",
        ha="center",
        fontsize=20,
        fontweight="bold",
        color=_INK,
    )
    fig.text(
        0.5,
        0.912,
        "Zonal statistics turn AI rasters into the two highest-weighted FPPS inputs: "
        "flood likelihood (0.30) + exposure (0.25).",
        ha="center",
        fontsize=11,
        color=_MUT,
    )

    bimg = _img(prev_dir, "D_buildings.png")
    axm = fig.add_axes([0.03, 0.10, 0.36, 0.74])
    axm.imshow(bimg)
    axm.axis("off")
    axm.set_title("SAR flood + exposed buildings, by sub-district", fontsize=12, color=_INK)
    h, w = bimg.shape[:2]
    axm.plot([w / 2, w / 2], [0, h], color="white", lw=1.6, alpha=0.8)
    axm.plot([0, w], [h / 2, h / 2], color="white", lw=1.6, alpha=0.8)
    placed = False
    if subs and bbox:
        # Real geometry: outline each sub-district and badge its true centroid.
        left, bottom, right, top = bbox

        def to_px(lon, lat):
            return (lon - left) / (right - left) * w, (top - lat) / (top - bottom) * h

        action_by_name = {
            str(r["subdistrict_name"]).split(" (")[0]: r["action_class"] for _, r in df.iterrows()
        }
        for f in subs.get("features", []):
            g = f["geometry"]
            polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
            pts = []
            for poly in polys:
                ring = poly[0]
                xs, ys = zip(*[to_px(x, y) for x, y in ring], strict=False)
                axm.plot(xs, ys, color="#eab308", lw=1.0, alpha=0.85)
                pts.extend(ring)
            nm = str(f["properties"].get("subdistrict_name", "")).split(" (")[0]
            act = action_by_name.get(nm)
            if act and pts:
                cx = sum(p[0] for p in pts) / len(pts)
                cy = sum(p[1] for p in pts) / len(pts)
                px, py = to_px(cx, cy)
                axm.text(
                    px,
                    py,
                    act,
                    ha="center",
                    va="center",
                    fontsize=12,
                    fontweight="bold",
                    color="white",
                    bbox=dict(
                        boxstyle="circle,pad=0.28", fc=_ACT.get(act, "#888"), ec="white", lw=1.2
                    ),
                )
                placed = True
    if not placed and not subs:
        quad_pos = {
            "Mae Sai": (0.25, 0.25),
            "Wiang Phang Kham": (0.75, 0.25),
            "Ko Chang": (0.25, 0.75),
            "Ban Sai Lom": (0.75, 0.75),
        }
        for _, r in df.iterrows():
            nm = str(r["subdistrict_name"]).split(" (")[0]
            if nm in quad_pos:
                x, y = quad_pos[nm]
                axm.text(
                    x * w,
                    y * h,
                    r["action_class"],
                    ha="center",
                    va="center",
                    fontsize=17,
                    fontweight="bold",
                    color="white",
                    bbox=dict(
                        boxstyle="circle,pad=0.32",
                        fc=_ACT.get(r["action_class"], "#888"),
                        ec="white",
                        lw=1.5,
                    ),
                )

    axf = fig.add_axes([0.40, 0.10, 0.16, 0.74])
    axf.axis("off")
    steps = [
        "SAR flood\nprobability",
        "+ Susceptibility\nsurface",
        "+ Building\nfootprints",
        "zonal stats\nper sub-district",
        "FPPS 0-100\n+ action A-E",
    ]
    cols = ["#38bdf8", "#f59e0b", "#64748b", _ACCENT, "#10b981"]
    for i, (s, c) in enumerate(zip(steps, cols, strict=False)):
        y = 0.86 - i * 0.19
        axf.add_patch(
            FancyBboxPatch(
                (0.08, y - 0.07),
                0.84,
                0.13,
                transform=axf.transAxes,
                boxstyle="round,pad=0.01,rounding_size=0.03",
                fc=c,
                ec="none",
                alpha=0.92,
            )
        )
        axf.text(
            0.5,
            y - 0.005,
            s,
            transform=axf.transAxes,
            ha="center",
            va="center",
            fontsize=9.3,
            color="white",
            fontweight="bold",
        )
        if i < len(steps) - 1:
            axf.annotate(
                "",
                xy=(0.5, y - 0.10),
                xytext=(0.5, y - 0.07),
                transform=axf.transAxes,
                arrowprops=dict(arrowstyle="-|>", color=_MUT, lw=2),
            )

    axt = fig.add_axes([0.575, 0.10, 0.40, 0.74])
    axt.axis("off")
    axt.set_title("AI-derived sub-district priority", fontsize=12, color=_INK, loc="left")
    cols_t = [
        ("subdistrict_name", "Sub-district"),
        ("flood_likelihood_0_100", "Flood\nlik."),
        ("exposure_0_100", "Expo\nsure"),
        ("fpps_0_100", "FPPS"),
        ("action_class", "Act"),
        ("confidence_class", "Conf."),
    ]
    dfx = df.sort_values("fpps_0_100", ascending=False)
    ytop = 0.88
    rh = 0.135
    xs = [0.0, 0.40, 0.53, 0.66, 0.79, 0.88]
    for j, (_key, lbl) in enumerate(cols_t):
        axt.text(
            xs[j],
            ytop + 0.06,
            lbl,
            transform=axt.transAxes,
            fontsize=9.3,
            color=_MUT,
            fontweight="bold",
            va="bottom",
        )
    for i, (_, r) in enumerate(dfx.iterrows()):
        y = ytop - i * rh
        axt.add_patch(
            Rectangle(
                (-0.01, y - 0.055),
                1.02,
                0.115,
                transform=axt.transAxes,
                fc="#f4f7fc" if i % 2 == 0 else "white",
                ec="#e2e8f0",
                lw=0.6,
            )
        )
        nm = str(r["subdistrict_name"]).split(" (")[0]
        axt.text(
            xs[0],
            y,
            nm,
            transform=axt.transAxes,
            fontsize=10,
            color=_INK,
            va="center",
            fontweight="bold",
        )
        axt.text(
            xs[1],
            y,
            f"{r['flood_likelihood_0_100']:.0f}",
            transform=axt.transAxes,
            fontsize=10,
            va="center",
            color="#25324a",
        )
        axt.text(
            xs[2],
            y,
            f"{r['exposure_0_100']:.0f}",
            transform=axt.transAxes,
            fontsize=10,
            va="center",
            color="#25324a",
        )
        axt.text(
            xs[3],
            y,
            f"{r['fpps_0_100']:.0f}",
            transform=axt.transAxes,
            fontsize=11,
            va="center",
            fontweight="bold",
            color=_INK,
        )
        axt.text(
            xs[4],
            y,
            r["action_class"],
            transform=axt.transAxes,
            fontsize=12,
            va="center",
            ha="center",
            fontweight="bold",
            color="white",
            bbox=dict(
                boxstyle="circle,pad=0.22", fc=_ACT.get(r["action_class"], "#888"), ec="none"
            ),
        )
        axt.text(
            xs[5],
            y,
            r["confidence_class"],
            transform=axt.transAxes,
            fontsize=9,
            va="center",
            color=_MUT,
        )
    axt.text(
        0.0,
        ytop - len(dfx) * rh - 0.02,
        "A Protect lives · B Keep routes open · C Essential "
        "services · D Build resilience · E Monitor",
        transform=axt.transAxes,
        fontsize=8.4,
        color=_MUT,
        va="top",
    )
    fig.text(
        0.5,
        0.02,
        "Confidence = agreement between two independent AI signals (SAR change vs terrain). "
        + (
            "Real Mae Sai data · not an official warning."
            if is_real
            else "Synthetic demo scene · not an official warning."
        ),
        ha="center",
        fontsize=9.3,
        color=_MUT,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return out_path
