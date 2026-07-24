"""Component G — Narrative generation (vision-language model, Moondream).

Anchor: *Introduction to GeoAI* (Wu, 2026), Ch. 15 §15.7-15.8. A compact VLM
(Moondream) captions / answers questions about remote-sensing imagery. FloodGuard
uses it to auto-draft plain-language captions for the before/after flood imagery
shown to non-technical decision-makers (Round-2 Communication criterion).

Assistive drafting only: every caption is a candidate to be reviewed and edited
by the team, never an autonomous claim. Runs on CPU (slow); kept optional.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class NarrativeResult:
    captions: dict[str, str]
    metrics: dict


DEFAULT_PROMPTS = {
    "sar_post": "Describe the water and terrain visible in this radar image of a river valley.",
    "flood_map": "Describe the flooded areas and settlements shown in this map for emergency planning.",
    "susceptibility": "Describe which parts of this terrain are most likely to flood.",
}


def generate_captions(
    images: dict[str, str | Path],
    output_path: str | Path,
    *,
    model_name: str = "vikhyatk/moondream2",
    prompts: dict[str, str] | None = None,
    length: str = "short",
) -> NarrativeResult:
    """Caption the given images with Moondream; write a reviewed-draft JSON."""

    import json

    import geoai

    from PIL import Image

    prompts = {**DEFAULT_PROMPTS, **(prompts or {})}
    captions: dict[str, str] = {}
    for label, path in images.items():
        question = prompts.get(label, "Describe this image for flood emergency planning.")
        try:
            # Pass a decoded PIL image (a bare path string FileNotFounds inside the
            # geoai moondream wrapper); RGB is required for the vision encoder.
            image = Image.open(path).convert("RGB")
            # geoai signature is moondream_query(question, source) -- question first.
            answer = geoai.moondream_query(question, image, model_name=model_name)
            captions[label] = str(answer).strip()
        except Exception as exc:  # pragma: no cover - VLM optional/slow
            captions[label] = f"[caption unavailable: {type(exc).__name__}]"

    payload = {
        "data_mode": "real_licensed_inputs",
        "model": f"Moondream ({model_name})",
        "review_status": "draft_for_human_review",
        "captions": captions,
        "assumptions": (
            "Auto-drafted plain-language captions from a vision-language model, "
            "for the communication layer only. Every caption must be reviewed and "
            "edited by the team before publication; not an autonomous claim and not "
            "an official warning."
        ),
    }
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return NarrativeResult(
        captions=captions,
        metrics={"data_mode": "real_licensed_inputs", "caption_count": len(captions),
                 "model": payload["model"], "review_status": "draft_for_human_review"},
    )
