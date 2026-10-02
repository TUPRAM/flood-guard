"""Season-envelope comparison for a case replay: how a modelled water mask and a season envelope overlap.

A *season envelope* is the area an agency product maps as water at some time in a season (for the Mae Sai replay,
UNOSAT/GISTDA product 4009: accumulated water, August to October 2024). It has no date per patch, so it is a
scenario layer (lane ``SCN-ENV``) and never an observation for a replay day. Setting the modelled water beside it
says where the two differ. It is a plausibility comparison: the envelope also holds water from other weeks of the
season and the modelled stages are illustrative, so neither mask is a reference for the other.

Everything here is a pure function on arrays that already share one grid, or on plain values. Nothing opens a
file, and nothing computes a Flood Preparedness Priority Score or an action class. The three ratios are named for
what they are:

* ``agreement_iou``: overlap divided by union;
* ``containment_model_in_envelope``: the share of the modelled water that lies inside the envelope;
* ``containment_envelope_in_model``: the share of the envelope that the modelled water reaches.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import re
from typing import Any

import numpy as np

from floodguard.replay_manifest import ENVELOPE_CHECK_ROLE

ENVELOPE_LANE = "SCN-ENV"
"""Evidence lane of a season envelope and of everything derived from it."""

COMPARISON_ROLE = ENVELOPE_CHECK_ROLE
"""Role of the comparison in a replay manifest's external checks: never an independent check."""

COMPARISON_USE = "Plausibility against a season envelope, not a validation."
"""The sentence every published comparison carries."""

AGREEMENT_KEYS: tuple[str, ...] = ("agreement_iou", "containment_model_in_envelope", "containment_envelope_in_model")
"""The three ratios of :func:`mask_agreement`, each between 0 and 1 (or ``None`` without a denominator)."""

RESIDENT_COUNT_RULES: dict[str, str] = {
    "residents_in_envelope": "rule",
    "residents_in_envelope_replay_rule": "replay_rule",
}
"""The two counts of residents inside an envelope and the key that states the rule of each.

``residents_in_envelope`` follows the planning overlay's exposure definition (population cells whose centre lies
inside the envelope); ``residents_in_envelope_replay_rule`` follows the replay's own rule, so that it can be set
beside the replay's residents in water. A published document gives both, each with its rule.
"""

_PLACEHOLDER = re.compile(r"\{[^{}]*\}")
_MISNAMED_KEY = re.compile(r"precision|recall|accura|validat|corroborat|fpps|action[_-]?class|priority[_-]?score", re.IGNORECASE)


class SeasonEnvelopeError(ValueError):
    """Raised when a season-envelope figure or document cannot be published as it stands."""


def _masks(*arrays: Any) -> list[np.ndarray]:
    masks = [np.asarray(array, dtype=bool) for array in arrays]
    shapes = {mask.shape for mask in masks}
    if len(shapes) != 1:
        raise SeasonEnvelopeError(f"every mask must share one grid; got shapes {sorted(shapes)}")
    return masks


def _ratio(numerator: float, denominator: float, digits: int = 3) -> float | None:
    return round(numerator / denominator, digits) if denominator > 0 else None


def mask_agreement(model: Any, envelope: Any, cell_km2: float, area: Any | None = None, digits: int = 2) -> dict[str, float | None]:
    """Overlap of a modelled water mask and a season-envelope mask on one grid, inside ``area``.

    ``model`` and ``envelope`` are boolean arrays of one shape; ``area`` (same shape) limits the count, for example
    to a district or one subdistrict, and defaults to the whole grid. ``cell_km2`` is the area of one cell.

    Returns the two areas, their overlap and union, the part only one mask holds, and the three ratios of
    :data:`AGREEMENT_KEYS`. A ratio is ``None`` when its denominator is zero: with no modelled water there is no
    share of it inside the envelope, which is not the same as zero.
    """
    if not cell_km2 > 0:
        raise SeasonEnvelopeError("cell_km2 must be positive")
    if area is None:
        model_mask, envelope_mask = _masks(model, envelope)
    else:
        model_mask, envelope_mask, area_mask = _masks(model, envelope, area)
        model_mask, envelope_mask = model_mask & area_mask, envelope_mask & area_mask
    model_cells = int(np.count_nonzero(model_mask))
    envelope_cells = int(np.count_nonzero(envelope_mask))
    overlap_cells = int(np.count_nonzero(model_mask & envelope_mask))
    union_cells = model_cells + envelope_cells - overlap_cells
    km2 = lambda cells: round(cells * cell_km2, digits)  # noqa: E731
    return {
        "model_km2": km2(model_cells),
        "envelope_km2": km2(envelope_cells),
        "overlap_km2": km2(overlap_cells),
        "union_km2": km2(union_cells),
        "model_only_km2": km2(model_cells - overlap_cells),
        "envelope_only_km2": km2(envelope_cells - overlap_cells),
        "agreement_iou": _ratio(overlap_cells, union_cells),
        "containment_model_in_envelope": _ratio(overlap_cells, model_cells),
        "containment_envelope_in_model": _ratio(overlap_cells, envelope_cells),
    }


def zone_areas(mask: Any, zones: Any, zone_ids: Sequence[str], cell_km2: float, digits: int = 3) -> dict[str, float]:
    """Area of ``mask`` inside each zone, keyed by zone id.

    ``zones`` holds ``index + 1`` of ``zone_ids`` for a cell inside that zone and 0 outside every zone.
    """
    mask_array, zone_array = np.asarray(mask, dtype=bool), np.asarray(zones)
    if mask_array.shape != zone_array.shape:
        raise SeasonEnvelopeError("the mask and the zones must share one grid")
    counts = np.bincount(zone_array[mask_array].ravel().astype(np.int64), minlength=len(zone_ids) + 1)
    return {zone_id: round(float(counts[index + 1]) * cell_km2, digits) for index, zone_id in enumerate(zone_ids)}


def zone_agreement(model: Any, envelope: Any, zones: Any, zone_ids: Sequence[str], cell_km2: float) -> list[dict[str, Any]]:
    """:func:`mask_agreement` for every zone of ``zones``, in the order of ``zone_ids`` (each row carries its ``zone_id``)."""
    zone_array = np.asarray(zones)
    return [{"zone_id": zone_id, **mask_agreement(model, envelope, cell_km2, zone_array == index + 1)}
            for index, zone_id in enumerate(zone_ids)]


def largest_differences(rows: Iterable[Mapping[str, Any]], key: str, minimum_km2: float = 0.5, limit: int = 3) -> list[str]:
    """Zone ids ordered by ``key`` (an area in km2, largest first), keeping at most ``limit`` zones of at least ``minimum_km2``.

    Used to say where the two masks differ most: ``envelope_only_km2`` names the zones with envelope water the model
    lacks, ``model_only_km2`` those with modelled water outside the envelope. Ties keep the order of ``rows``.
    """
    ranked = sorted((row for row in rows if (row.get(key) or 0) >= minimum_km2), key=lambda row: -float(row[key]))
    return [str(row["zone_id"]) for row in ranked[:limit]]


def share_inside(part: Any, envelope: Any, area: Any | None = None) -> float | None:
    """Share of the cells of ``part`` (inside ``area``) that lie inside ``envelope``; ``None`` when ``part`` is empty."""
    if area is None:
        part_mask, envelope_mask = _masks(part, envelope)
    else:
        part_mask, envelope_mask, area_mask = _masks(part, envelope, area)
        part_mask = part_mask & area_mask
    return _ratio(int(np.count_nonzero(part_mask & envelope_mask)), int(np.count_nonzero(part_mask)))


def residents_inside(mask: Any, residents_per_cell: Any, area: Any | None = None) -> int:
    """Residents on the cells of ``mask`` (inside ``area``), as a whole number.

    ``residents_per_cell`` is a population grid on the same cells (for the replay, WorldPop 2020 spread evenly over
    10 m cells): the same exposure rule as the replay's residents in water, a cell counting when it is in the mask.
    """
    population = np.asarray(residents_per_cell, dtype=np.float64)
    cells = np.asarray(mask, dtype=bool)
    if cells.shape != population.shape:
        raise SeasonEnvelopeError("the mask and the population grid must share one grid")
    if area is not None:
        area_mask = np.asarray(area, dtype=bool)
        if area_mask.shape != cells.shape:
            raise SeasonEnvelopeError("the mask and the area must share one grid")
        cells = cells & area_mask
    if np.any(population[cells] < 0):
        raise SeasonEnvelopeError("a population grid cannot hold a negative count")
    return int(round(float(population[cells].sum())))


def fill_change_notice(template: str, *, clip_geometry: str, repair_method: str, repair_count: int, source_crs: str,
                       target_crs: str, cell_size_m: float | int | str) -> str:
    """Fill a rights record's change-notice template for one derived file.

    A derived file states its own values for the four changes the record lists (clip, geometry repair, reprojection,
    rasterisation). A template with another placeholder, or a value left empty, is refused: a shipped notice never
    carries a raw ``{...}``.
    """
    if not isinstance(repair_count, int) or isinstance(repair_count, bool) or repair_count < 0:
        raise SeasonEnvelopeError("repair_count must be a whole number of repaired parts")
    values = {"clip_geometry": clip_geometry, "repair_method": repair_method, "repair_count": repair_count,
              "source_crs": source_crs, "target_crs": target_crs, "cell_size_m": cell_size_m}
    if any(isinstance(value, str) and not value.strip() for value in values.values()):
        raise SeasonEnvelopeError("every change-notice value must be stated")
    try:
        notice = template.format(**values)
    except (KeyError, IndexError, ValueError) as exc:
        raise SeasonEnvelopeError(f"the change-notice template has a placeholder this file cannot fill: {exc}") from exc
    if _PLACEHOLDER.search(notice):
        raise SeasonEnvelopeError("the change notice still holds a placeholder")
    return notice


OTHER_INPUT_KEYS: tuple[str, ...] = ("id", "name", "licence", "attribution", "used_for")
"""What a derived file states about each input that is not the agency product (see :func:`other_input_problems`)."""


def other_input_problems(inputs: Any) -> list[str]:
    """Why a list of other inputs may not be published (empty when it may).

    A statistics file derived from an agency product also holds figures from other open data (for the replay: the
    modelled water from a terrain model, residents from a population grid, subdistrict areas from boundary data).
    Each of those inputs keeps its own credit and licence, so each entry states its ``name``, its ``licence``, its
    ``attribution`` and what it was ``used_for``, with an ``id``. At least one entry is needed.
    """
    if not isinstance(inputs, Sequence) or isinstance(inputs, (str, bytes)) or not inputs:
        return ["other_inputs must list every input besides the product, each with its licence and its credit"]
    problems = []
    for index, item in enumerate(inputs):
        for key in OTHER_INPUT_KEYS:
            if not isinstance(item, Mapping) or not isinstance(item.get(key), str) or not item[key].strip():
                problems.append(f"other_inputs[{index}] lacks {key}")
    return problems


def licence_notice(*, title: str, files: Sequence[str], licence: Mapping[str, Any], credit: str, change_notices: Mapping[str, str],
                   source_lines: Sequence[str], limits: Sequence[str], other_inputs: Sequence[Mapping[str, str]], other_inputs_note: str,
                   thai: Mapping[str, Any]) -> str:
    """Text of the ``LICENSE`` file that ships beside the derived files: licence, credit and what was changed.

    ``licence`` needs ``full_name``, ``name``, ``url`` and ``legal_code_url``. ``change_notices`` maps a file name
    to its change notice. ``other_inputs`` lists the inputs besides the product whose figures a covered file holds
    (:data:`OTHER_INPUT_KEYS`); ``other_inputs_note`` says that they keep their own credits and licences. ``thai``
    gives the Thai half: ``title``, ``headings`` (files, source, credit, licence, share_alike, changes, other_inputs,
    limits), ``source_lines``, ``share_alike``, ``limits``, ``change_notices`` (the Thai rendering of each file's
    notice), ``other_inputs_note``, ``other_inputs_used_for`` (input id to Thai text) and ``other_inputs_labels``
    (``licence``, ``credit``, ``used_for``). The credit, the licence names, the input names and the links are
    repeated as published; in the Thai half each change notice is given in Thai, followed by the English notice as
    published. The two halves are separated by a line of dashes, as in the rights record's own notice. Lines end
    with LF.
    """
    for name in ("full_name", "name", "url", "legal_code_url"):
        if not str(licence.get(name, "")).strip():
            raise SeasonEnvelopeError(f"the licence notice needs licence.{name}")
    if not credit.strip() or not files or not change_notices:
        raise SeasonEnvelopeError("the licence notice needs a credit, the files it covers and their change notices")
    missing = [name for name in change_notices if name not in files]
    if missing:
        raise SeasonEnvelopeError(f"a change notice names a file the notice does not cover: {missing}")
    problems = other_input_problems(other_inputs)
    if problems or not other_inputs_note.strip():
        raise SeasonEnvelopeError(f"the licence notice needs the other inputs with their licences and credits: {problems}")
    thai_notices = thai.get("change_notices") or {}
    untranslated = [name for name in change_notices if not str(thai_notices.get(name, "")).strip()]
    if untranslated:
        raise SeasonEnvelopeError(f"the Thai half needs a Thai change notice for: {untranslated}")
    thai_used_for = thai.get("other_inputs_used_for") or {}
    unnamed = [item["id"] for item in other_inputs if not str(thai_used_for.get(item["id"], "")).strip()]
    if unnamed or not str(thai.get("other_inputs_note", "")).strip():
        raise SeasonEnvelopeError(f"the Thai half needs the note on the other inputs and what each was used for: {unnamed}")

    def half(heading: Mapping[str, str], head: str, sources: Sequence[str], share_alike: str, limit_lines: Sequence[str],
             notices: Mapping[str, Sequence[str]], inputs_note: str, labels: Mapping[str, str], used_for: Mapping[str, str]) -> list[str]:
        lines = ["FloodGuard Thailand", head, "", f"1. {heading['files']}", *(f"   - {name}" for name in files), "",
                 f"2. {heading['source']}", *(f"   {line}" for line in sources), "",
                 f"3. {heading['credit']}", f"   {credit}", "",
                 f"4. {heading['licence']}", f"   {licence['full_name']} ({licence['name']})", f"   {licence['url']}",
                 f"   {licence['legal_code_url']}", "",
                 f"5. {heading['share_alike']}", f"   {share_alike}", "",
                 f"6. {heading['changes']}"]
        for name, texts in notices.items():
            lines += [f"   {name}:", *(f"   {text}" for text in texts)]
        lines += ["", f"7. {heading['other_inputs']}", f"   {inputs_note}"]
        for item in other_inputs:
            lines += [f"   - {item['name']}", f"     {labels['licence']}: {item['licence']}", f"     {labels['credit']}: {item['attribution']}",
                      f"     {labels['used_for']}: {used_for[item['id']]}"]
        lines += ["", f"8. {heading['limits']}", *(f"   - {line}" for line in limit_lines)]
        return lines

    english = half(
        {"files": "Files this notice covers", "source": "Source", "credit": "Credit", "licence": "Licence", "share_alike": "ShareAlike",
         "changes": "Changes made by FloodGuard (change notice)", "other_inputs": "Other inputs (their own credits and licences)",
         "limits": "Limits"},
        title, source_lines,
        ("You may copy, share and adapt these files if you give the credit above, link to the licence, say what you changed "
         f"and share your version under the same licence, {licence['name']}."),
        limits, {name: [notice] for name, notice in change_notices.items()}, other_inputs_note,
        {"licence": "Licence", "credit": "Credit", "used_for": "Used for"}, {item["id"]: item["used_for"] for item in other_inputs})
    thai_half = half(thai["headings"], thai["title"], thai["source_lines"], thai["share_alike"], thai["limits"],
                     {name: [thai_notices[name], notice] for name, notice in change_notices.items()}, thai["other_inputs_note"],
                     thai["other_inputs_labels"], thai_used_for)
    return "\n".join([*english, "", "-" * 80, "", *thai_half]) + "\n"


def credit_holders(credit: str) -> str:
    """The holders a credit names first: its text before the first comma.

    "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009" gives "UNOSAT and GISTDA". A short credit (on a map, or
    in an exported picture) must name these holders, never the licence alone.
    """
    return str(credit).split(",", 1)[0].strip()


def document_problems(document: Mapping[str, Any], *, licence_name: str, credit: str) -> list[str]:
    """Why a season-envelope document (``envelope.json``) may not be published (empty when it may).

    The document must sit in the ``SCN-ENV`` lane and say it is not an observation for any replay day; carry the
    licence ``licence_name``, the credit ``credit``, a map credit that names the licence and the credit's holders,
    the standard sentence (used as provided, not validated by FloodGuard) and a filled change notice; list its other
    inputs with their licences and credits (:func:`other_input_problems`); carry ``source_timestamp``,
    ``generated_at``, a confidence with its reason, and assumptions; state the plausibility sentence; name its
    ratios with :data:`AGREEMENT_KEYS` and keep each between 0 and 1; and hold no key that names a precision, a
    recall, an accuracy, a validation, a score or an action class.
    """
    problems: list[str] = []
    if document.get("lane") != ENVELOPE_LANE:
        problems.append(f"lane must be {ENVELOPE_LANE}")
    if document.get("not_an_observation_for_any_replay_day") is not True:
        problems.append("the document must state that the envelope is not an observation for any replay day")
    licence = document.get("licence")
    if not isinstance(licence, Mapping) or licence.get("name") != licence_name or not licence.get("url"):
        problems.append(f"licence must be {licence_name} with its link")
    if document.get("credit") != credit:
        problems.append("credit must be the rights record's attribution text")
    map_credit = str(document.get("map_credit", ""))
    if licence_name not in map_credit:
        problems.append("map_credit must name the licence")
    holders = credit_holders(credit)
    if not holders or holders not in map_credit:
        problems.append("map_credit must name the holders of the product, as the credit begins")
    sentence = document.get("standard_sentence")
    if not isinstance(sentence, str) or "did not validate" not in sentence or licence_name not in sentence:
        problems.append("standard_sentence must say that the product is used as provided under its licence and that FloodGuard did not validate it")
    problems.extend(other_input_problems(document.get("other_inputs")))
    comparison = document.get("comparison")
    notices = {"change_notice": document.get("change_notice"),
               "comparison.change_notice": comparison.get("change_notice") if isinstance(comparison, Mapping) else None}
    for name, notice in notices.items():
        if not isinstance(notice, str) or not notice.strip() or _PLACEHOLDER.search(notice) or credit not in notice or licence_name not in notice:
            problems.append(f"{name} must be filled and name the credit and the licence")
    for key in ("source_timestamp", "generated_at", "confidence", "confidence_reason", "season_window"):
        if not isinstance(document.get(key), str) or not document[key].strip():
            problems.append(f"missing {key}")
    if not isinstance(document.get("assumptions"), list) or not document["assumptions"]:
        problems.append("missing assumptions")
    if document.get("official_warning") is not False or document.get("operational_status") != "non_operational" or document.get("can_feed_decision_layer") is not False:
        problems.append("the document must be non-operational, not an official warning and unable to feed the decision layer")
    if not isinstance(comparison, Mapping):
        problems.append("missing comparison")
    else:
        if comparison.get("role") != COMPARISON_ROLE:
            problems.append(f"comparison.role must be {COMPARISON_ROLE}")
        if COMPARISON_USE.lower()[:-1] not in str(comparison.get("use", "")).lower():
            problems.append("comparison.use must say: plausibility against a season envelope, not a validation")
        rows = [*(comparison.get("district") or []), *(comparison.get("by_tambon") or [])]
        if not comparison.get("district"):
            problems.append("comparison.district must hold at least one row")
        for row in rows:
            for key in AGREEMENT_KEYS:
                value = row.get(key) if isinstance(row, Mapping) else None
                if key not in row or (value is not None and not 0 <= value <= 1):
                    problems.append(f"comparison row {row.get('id') or row.get('tambon_id')}: {key} must be a share between 0 and 1, or null")
        residents = comparison.get("residents")
        if residents is not None:
            # Two rules give two counts of the residents inside the envelope; a count without its rule cannot be compared.
            for count, rule in RESIDENT_COUNT_RULES.items():
                if not isinstance(residents, Mapping) or count not in residents or not isinstance(residents.get(rule), str) or not residents[rule].strip():
                    problems.append(f"comparison.residents must give {count} with its rule in {rule}")
    problems.extend(f"{path} names a measure the comparison does not claim" for path in _misnamed_keys(document))
    return problems


def _misnamed_keys(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            here = f"{path}.{key}"
            if _MISNAMED_KEY.search(str(key)) and key != "field_validation":
                found.append(here)
            found.extend(_misnamed_keys(item, here))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_misnamed_keys(item, f"{path}[{index}]"))
    return found
