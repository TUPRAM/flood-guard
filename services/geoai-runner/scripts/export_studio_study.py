"""Export frozen public experiment evidence for Studio; stdlib only, no fitting or network.

Public downloads preserve numeric evidence but replace experiment-root absolute paths
with repository-relative paths. Source and exported byte hashes remain distinct.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

STUDY = "c2s-ms-20260915"
REVISION = "r1"
BASE = f"/studies/{STUDY}/{REVISION}/"
EVIDENCE = "services/geoai-runner/evidence/"
ARCHIVE = EVIDENCE + "public-ml-results/"
WORK = "outputs/geoai/work/public-training/"
SAFETY = {
    "aggregation_status": "report_only",
    "operational_status": "non_operational",
    "can_feed_decision_layer": False,
    "official_warning": False,
    "confidence": "research_candidate_not_operationally_validated",
}
ROLE_PURPOSE = {
    "train": "Fit model parameters and event-grouped tree-model search.",
    "tune": "Choose the U-Net checkpoint; not the final test set.",
    "calibration": "Fit probability calibration after model fitting.",
    "selection": "Freeze confidence abstention policies before test evaluation.",
    "test": "Evaluate frozen models and policies on entire held-out events.",
}
METRICS = (
    "iou", "f1_dice", "precision", "recall", "brier", "ece", "error_rate",
    "n_pixels", "n_reference_positive", "true_positive", "false_positive",
    "true_negative", "false_negative", "reliability",
)
PRIVATE_PATH = re.compile(r"(?:^|[^A-Za-z0-9_])[A-Za-z]:[\\/]|file://|/(?:Users|home|root)/")
SENSITIVE_QUERY = {"sig", "token", "access_token", "api_key", "key", "password"}


def digest(body: bytes) -> str:
    """Return the SHA-256 of exact bytes."""
    return hashlib.sha256(body).hexdigest()


def encoded(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False,
                       allow_nan=False, separators=(",", ":")) + "\n").encode()


def public_safe(value: Any, root: Path) -> Any:
    """Normalize only known local-root paths; reject other private paths or tokens."""
    if isinstance(value, dict):
        return {key: public_safe(item, root) for key, item in value.items()}
    if isinstance(value, list):
        return [public_safe(item, root) for item in value]
    if isinstance(value, str):
        result = value.replace("\\", "/")
        prefix = root.as_posix().rstrip("/") + "/"
        result = result.replace(prefix, "")
        if PRIVATE_PATH.search(result) or result.startswith("//"):
            raise ValueError("A private path outside the experiment root cannot be published")
        for url in re.findall(r"https?://[^\s\"<>]+", result):
            parsed = urlsplit(url)
            if parsed.username or parsed.password or SENSITIVE_QUERY.intersection(
                key.lower() for key in parse_qs(parsed.query)
            ):
                raise ValueError("Authenticated URLs cannot be published")
        return result
    return value


def envelope(kind: str, **values: Any) -> dict[str, Any]:
    return {**SAFETY, "schema_version": f"floodguard.study-{kind}.v1",
            "study_id": STUDY, "revision": REVISION,
            "data_mode": "public_benchmark_report_projection",
            "source_timestamp": "2016-08-12T23:46:51Z/2020-10-20T16:42:47Z",
            "assumptions": ["Separate public research report; no decision-layer authorization."],
            "license": {"c2sms": "CC-BY-4.0", "esa-worldcover": "CC-BY-4.0",
                        "cop-dem-glo-30": "Copernicus DEM GLO-30 full, free and open licence",
                        "jrc-gsw": "Copernicus free use with attribution", "sentinel-1-rtc": "CC-BY-4.0"},
            **values}


class Exporter:
    """Collect deterministic, independently hashed public projections."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.files: dict[str, bytes] = {}
        self.assets: list[dict[str, Any]] = []
        self.provenance: dict[str, dict[str, Any]] = {}

    def read(self, relative: str, expected: dict[str, Any] | None = None) -> Any:
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root) or path.suffix != ".json":
            raise ValueError("Source must be a JSON file inside the experiment root")
        body = path.read_bytes()
        if expected and (len(body) != expected["bytes"] or digest(body) != expected["sha256"]):
            raise ValueError(f"Source receipt mismatch: {relative}")
        self.provenance[relative] = {
            "source_path": relative, "bytes": len(body), "sha256": digest(body),
        }
        return json.loads(body)

    def asset(self, name: str, value: Any, label: str,
              source: str | None = None) -> dict[str, Any]:
        body = encoded(public_safe(value, self.root))
        if name in self.files and self.files[name] != body:
            raise ValueError(f"Conflicting public asset: {name}")
        self.files[name] = body
        asset = {
            "href": BASE + name, "bytes": len(body), "sha256": digest(body),
            "label": label, "media_type": "application/json",
            "source_sha256": self.provenance[source]["sha256"] if source else None,
            "transformation": (
                "Public JSON reserialization; experiment-root paths made relative; "
                "all numeric evidence retained. Original and public hashes differ."
                if source else "Derived public study projection; source receipts retained."
            ),
        }
        self.assets.append(asset)
        return asset

    def download(self, relative: str, name: str, expected: dict[str, Any] | None = None
                 ) -> tuple[Any, dict[str, Any]]:
        value = self.read(relative, expected)
        return value, self.asset("downloads/" + name, value, name, relative)

    def existing_asset(self, output: Path, name: str, label: str) -> dict[str, Any] | None:
        """Bind an independently generated display artifact without changing its bytes."""
        path = output / name
        if not path.exists():
            return None
        body = path.read_bytes()
        value = json.loads(body)
        if public_safe(value, self.root) != value:
            raise ValueError("Display artifact still contains paths requiring redaction")
        if value.get("study_id") != STUDY or value.get("revision") != REVISION:
            raise ValueError("Display artifact belongs to another study revision")
        safety = (value.get("metadata", {}) if name == "visual-index.json"
                  and value.get("schema_version") == 1 else value)
        if (safety.get("official_warning") is not False
                or safety.get("can_feed_decision_layer") is not False
                or safety.get("aggregation_status") != "report_only"):
            raise ValueError("Display artifact is not report-only")
        asset = {"href": BASE + name, "sha256": digest(body), "bytes": len(body),
                 "label": label, "media_type": "application/json", "source_sha256": None,
                 "transformation": "Separately generated display artifact; original display bytes retained."}
        self.assets.append(asset)
        return asset


def receipt(value: dict[str, Any]) -> dict[str, Any]:
    return {"source_path": value.get("path", value.get("source_path")),
            "bytes": value["bytes"], "sha256": value["sha256"]}


def metrics(value: dict[str, Any]) -> dict[str, Any]:
    result = {key: value[key] for key in METRICS}
    counts = sum(result[key] for key in (
        "true_positive", "false_positive", "true_negative", "false_negative"))
    if counts != result["n_pixels"]:
        raise ValueError("Confusion matrix does not match support")
    return result


def score(value: dict[str, Any]) -> dict[str, Any]:
    return {"full_valid": metrics(value["full_valid"]),
            "selective": metrics(value["selective"]),
            "coverage": value["coverage"], "n_valid_pixels": value["n_valid_pixels"]}


def units(names: list[str]) -> dict[str, str]:
    known = {"vv_db": "dB", "vh_db": "dB", "vv_minus_vh_db": "dB",
             "slope_degrees": "degrees", "hand_proxy_m": "m (proxy)",
             "twi_proxy": "dimensionless (proxy)",
             "drainage_proxy_distance_m": "m (proxy)",
             "jrc_occurrence_percent": "%"}
    return {name: known.get(name, "binary indicator" if name.startswith("worldcover_")
                           else "not recorded") for name in names}


def make_events(inventory: dict[str, Any], partition: dict[str, Any]
                ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for chip in inventory["chips"]:
        grouped[chip["event_id"]].append(chip)
    if len(grouped) != 18 or len(inventory["chips"]) != 900:
        raise ValueError("This revision requires the complete 900-chip, 18-event inventory")
    if set(grouped) != set(partition["event_roles"]):
        raise ValueError("Partition events differ from inventory")
    events = []
    for event_id, chips in sorted(grouped.items()):
        bbox = partition["event_envelopes"][event_id]
        dates = sorted({chip["source_timestamp"] for chip in chips})
        countries = {"749aca10-a39b-4321-8322-100dd6f976d4": "Australia",
                     "975ecc1f-bc34-4005-b2df-ef45775f116d": "Nigeria",
                     "c19f5f27-2b3b-4b83-8f4a-cf9275d94cdd": "Pakistan"}
        events.append({
            "event_id": event_id, "role": partition["event_roles"][event_id],
            "country": countries.get(event_id),
            "country_source": ("docs/first_ml_experiment_results.md per-event results"
                               if event_id in countries else "not present in frozen chip metadata"),
            "bbox": bbox, "centroid_lon_lat": [(bbox[0] + bbox[2]) / 2,
                                                 (bbox[1] + bbox[3]) / 2],
            "n_chips": len(chips), "scene_ids": sorted({chip["scene_id"] for chip in chips}),
            "source_timestamps": dates, "source_start": dates[0], "source_end": dates[-1],
        })
    roles = [{"role": role, "n_events": len(selected),
              "n_chips": sum(event["n_chips"] for event in selected),
              "event_ids": [event["event_id"] for event in selected], "purpose": purpose}
             for role, purpose in ROLE_PURPOSE.items()
             for selected in [[event for event in events if event["role"] == role]]]
    if [role["n_chips"] for role in roles] != [443, 130, 98, 118, 111]:
        raise ValueError("Frozen role membership changed")
    return events, roles


def source_catalog(attribution: list[str]) -> list[dict[str, Any]]:
    specs = [
        ("c2sms", "C2S-MS Floods", "1.0", "Training and held-out water labels",
         "2016-08-12 to 2020-10-20", "CC-BY-4.0", attribution[0],
         [("Dataset and license", "https://radiantearth.blob.core.windows.net/mlhub/c2smsfloods/README.md"),
          ("Annotation method", "https://radiantearth.blob.core.windows.net/mlhub/c2smsfloods/ms-dataset_README.pdf"),
          ("Download registry", "https://registry.opendata.aws/c2smsfloods/")],
         ["Hand labels include permanent water, not only newly flooded land.",
          "Later explicit CC-BY-4.0 grant retained alongside older proprietary STAC and BY/BY-SA text conflicts."]),
        ("esa-worldcover", "ESA WorldCover", "2021 v200", "Land-cover context",
         "2021", "CC-BY-4.0", attribution[1],
         [("Publisher download", "https://esa-worldcover.org/en/data-access"),
          ("Version DOI", "https://doi.org/10.5281/zenodo.7254221")],
         ["Postdates C2S imagery; retrospective benchmark context."]),
        ("cop-dem-glo-30", "Copernicus DEM GLO-30", "2021 release", "Terrain context",
         "TanDEM-X surface model; 2021 release", "Copernicus DEM GLO-30 full, free and open licence",
         attribution[3] + " " + attribution[4],
         [("Publisher license", "https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/DEM/resources/license/License-COPDEM-30.pdf"),
          ("Public download registry", "https://registry.opendata.aws/copernicus-dem/")],
         ["Nominal 30 m surface model; resampling adds no new 10 m observations.",
          "HAND, TWI and drainage channels are approximations."]),
        ("jrc-gsw", "JRC Global Surface Water", "v1.3", "Long-term water occurrence",
         "1984-2020", "Copernicus free use with attribution", attribution[2],
         [("Publisher download and terms", "https://global-surface-water.appspot.com/download"),
          ("Pinned collection", "https://planetarycomputer.microsoft.com/api/stac/v1/collections/jrc-gsw")],
         ["Pinned v1.3, not latest; retrospective context, not flood truth.",
          "Eleven Australian test chips have no valid aligned occurrence support."]),
        ("sentinel-1-rtc", "Sentinel-1 RTC", "Planetary Computer gamma0 RTC",
         "Matched transfer comparison and Mae Sai inference", "Mae Sai: 2024-08-22 / 2024-09-15",
         "CC-BY-4.0", "Contains modified Copernicus Sentinel data; Planetary Computer RTC processing.",
         [("Collection and access", "https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-1-rtc")],
         ["SAS access required; RTC collection states account required.",
          "GRD-to-RTC transfer differs from original training representation."]),
    ]
    return [{"id": item[0], "name": item[1], "version": item[2], "purpose": item[3],
             "source_period": item[4], "license": item[5], "attribution": item[6],
             "links": [{"label": label, "href": href} for label, href in item[7]],
             "limitations": item[8]} for item in specs]


def export_study(root: Path, output: Path) -> dict[str, Any]:
    """Validate frozen receipts and export a complete versioned study atomically per file."""
    ex = Exporter(root)
    archive = ex.read(ARCHIVE + "index.json")
    summary = ex.read(EVIDENCE + "public-ml-results-summary.json")
    if archive["status"] != "complete_exact_copies_verified" or summary["status"] != "complete":
        raise ValueError("Experiment archive or summary is incomplete")
    records: dict[str, Any] = {}
    downloads: dict[str, Any] = {}
    for item in archive["files"]:
        path = item["archived"]["path"]
        relative = path.removeprefix(ARCHIVE)
        value, asset = ex.download(path, relative.replace("/", "-"), item["archived"])
        if value.get("official_warning") or value.get("can_feed_decision_layer"):
            raise ValueError("An experiment record exceeds report-only scope")
        records[relative], downloads[relative] = value, asset

    acquisition_path = EVIDENCE + "c2sms-acquisition-manifest.json"
    acquisition, _ = ex.download(acquisition_path, "acquisition-manifest.json")
    full_manifest = ex.read(acquisition["source_manifest"]["path"], acquisition["source_manifest"])
    inventory = ex.read(full_manifest["inventory_path"], {
        "bytes": (root / full_manifest["inventory_path"]).stat().st_size,
        "sha256": full_manifest["inventory_file_sha256"],
    })
    partition, _ = ex.download(EVIDENCE + "c2sms-event-partition.json", "event-partition.json")
    if ex.provenance[EVIDENCE + "c2sms-event-partition.json"]["sha256"] != full_manifest["partition_file_sha256"]:
        raise ValueError("Acquisition and partition are not bound")
    events, roles = make_events(inventory, partition)
    ex.asset("downloads/chip-inventory.json", inventory, "Frozen chip inventory",
             full_manifest["inventory_path"])

    benchmarks = []
    for key in sorted(summary["benchmarks"]):
        raw = records["results/" + key + ".json"]
        original_path = ARCHIVE + "results/" + key + ".json"
        summary_row = summary["benchmarks"][key]
        if summary_row["source"]["sha256"] != ex.provenance[original_path]["sha256"]:
            raise ValueError("Summary references a different benchmark")
        for version in ("raw", "calibrated"):
            for metric, value in summary_row[version]["full_valid"].items():
                if raw[version]["full_valid"][metric] != value:
                    raise ValueError("Published summary and source metric differ")
        invalid = sum(item["raw"]["n_valid_pixels"] == 0 for item in raw["per_chip"])
        row = {
            "id": key, "arm": raw["arm"], "model": raw["model"],
            "dataset": raw["dataset"], "source_timestamp": raw["source_timestamp"],
            "processed_utc": raw["processed_utc"], "inventory_chips": raw["n_test_chips"],
            "supported_chips": raw["n_test_chips"] - invalid, "invalid_chips": invalid,
            "n_test_events": raw["n_test_events"], "raw": score(raw["raw"]),
            "calibrated": score(raw["calibrated"]),
            "per_event": {event: {version: score(item[version]) for version in ("raw", "calibrated")}
                          for event, item in raw["per_event"].items()},
            "event_macro_iou": {
                version: summary_row["event_macro_iou"][version]["mean_iou"]
                for version in ("raw", "calibrated")
            } | {"n_events": raw["n_test_events"], "confidence_interval": "not_estimated"},
            "combined_screening": None,
            "calibration": raw["calibration"], "abstention": raw["abstention"],
            "source": ex.provenance[original_path], "download": downloads["results/" + key + ".json"],
        }
        combined = raw.get("combined_screening")
        if combined:
            row["combined_screening"] = {key: combined[key] for key in (
                "coverage_of_original_valid_pixels", "n_accepted_pixels", "n_context_vetoed",
                "n_original_valid_pixels")}
            row["combined_screening"]["metrics_on_accepted_pixels"] = metrics(combined["metrics_on_accepted_pixels"])
        meta_key = "models/" + key + ".json"
        meta = records.get(meta_key, raw.get("model_metadata"))
        training = None
        if meta:
            training = {
                "feature_names": meta.get("feature_names", []),
                "feature_units": units(meta.get("feature_names", [])),
                "checkpoint": receipt(meta["checkpoint"]) if meta.get("checkpoint") else None,
                "feature_manifest": receipt(meta["feature_manifest"]) if meta.get("feature_manifest") else None,
                "fit": meta.get("fit", meta), "sampling": meta.get("sampling"),
                "seed": meta.get("seed"), "download": downloads.get(meta_key),
            }
        shap = raw.get("tree_shap")
        shap_view = None if shap is None else {
            field: shap[field] for field in ("method", "n_samples", "role", "feature_names",
                                            "mean_absolute_contribution", "assumptions")
        } | {"feature_units": units(shap["feature_names"])}
        detail = envelope("model", benchmark=row, training=training, assumptions=raw["assumptions"],
                          risk_coverage_curve=raw["risk_coverage_curve"], tree_shap=shap_view,
                          per_chip=raw["per_chip"])
        row["detail"] = ex.asset("models/" + key.replace("/", "-") + ".json", detail, key + " detail")
        benchmarks.append(row)

    rtc_arms = []
    for arm in ("sar", "context"):
        key = "results/" + arm + "/rtc-comparison.json"
        raw = records[key]
        def methods(items: dict[str, Any]) -> dict[str, Any]:
            return {name: {version: score(item[version]) for version in ("raw", "calibrated")
                           if version in item}
                    for name, item in items.items()}
        rtc_arms.append({
            "arm": arm, **{field: raw[field] for field in (
                "common_valid_pixels", "n_paired_test_chips", "n_excluded_chips",
                "n_paired_events", "n_full_test_chips", "assumptions", "source_timestamp")},
            "pooled": methods(raw["pooled"]["methods"]),
            "per_event": {event: methods(value["methods"]) for event, value in raw["per_event"].items()},
            "source": ex.provenance[ARCHIVE + key], "download": downloads[key],
        })
    rtc_acq, _ = ex.download(EVIDENCE + "c2sms-rtc-test-acquisition.json", "rtc-acquisition.json")
    rtc_asset = ex.asset("rtc.json", envelope(
        "rtc", arms=rtc_arms, source_timestamp=rtc_arms[0]["source_timestamp"],
        assumptions=rtc_arms[1]["assumptions"], acquisition=rtc_acq), "Matched RTC comparison")

    inference = []
    pair = None
    for arm in ("sar", "context"):
        for model in ("random_forest", "xgboost", "unet"):
            key = f"{arm}/{model}"
            path = WORK + f"mae-sai/inference/{key}/manifest.json"
            raw, download = ex.download(path, "mae-sai-" + key.replace("/", "-") + ".json")
            if raw["metrics"] is not None or raw["accuracy_status"] != "unavailable_no_qualified_Thai_reference":
                raise ValueError("Mae Sai inference cannot contain accuracy claims")
            if raw["benchmark_results"]["sha256"] != ex.provenance[ARCHIVE + "results/" + key + ".json"]["sha256"]:
                raise ValueError("Mae Sai model refers to a different benchmark")
            pair = raw["rtc_pair"]
            inference.append({
                "id": key, **{field: raw[field] for field in (
                    "arm", "model", "source_timestamp", "processed_utc", "valid_pixels",
                    "accepted_pixels", "accuracy_status", "metrics", "grid", "calibration",
                    "abstention_policy", "context_screening")},
                "accepted_fraction": raw["accepted_pixels"] / raw["valid_pixels"],
                "layers": receipt(raw["layers"]), "benchmark_sha256": raw["benchmark_results"]["sha256"],
                "checkpoint_sha256": raw["model_metadata"]["checkpoint"]["sha256"],
                "source": ex.provenance[path], "download": download,
            })
    mae_asset = ex.asset("mae-sai.json", envelope(
        "mae-sai", records=inference, bands=["water_probability", "validity", "entropy", "abstention"],
        source_timestamp=inference[0]["source_timestamp"], source_pair=pair,
        accuracy_status="unavailable_no_qualified_Thai_reference", metrics=None,
        assumptions=["No qualified Thai reference exists; no Mae Sai accuracy is claimed.",
                     "Frozen GRD models and policies are applied to RTC without Thai fitting.",
                     "Prediction, validity, entropy and abstention are distinct layers.",
                     "Context uses dated land cover and water occurrence."]), "Mae Sai inference")

    for relative, name in [
        ("c2sms-context-acquisition.json", "context-acquisition.json"),
        ("c2sms-context-empty-test-chips.json", "context-empty-test-chips.json"),
        ("c2sms_alternative_probe.json", "dataset-license-provenance.json"),
    ]:
        ex.download(EVIDENCE + relative, name)
    geography = ex.existing_asset(output, "geography.json", "Display-only world geography")
    visuals = ex.existing_asset(output, "visual-index.json", "Frozen raster display index")
    study = envelope(
        "summary", title="C2S-MS water benchmark", dataset=summary["dataset"],
        data_mode="public_benchmark_report_projection", source_timestamp=acquisition["source_timestamp"],
        processed_utc=summary["processed_utc"], partition_frozen_utc=partition["frozen_utc"],
        counts={"chips": acquisition["n_chips"], "events": len(events),
                "scenes": len({chip["scene_id"] for chip in inventory["chips"]}),
                "files": acquisition["n_files"], "download_bytes": acquisition["total_bytes"]},
        events=events, roles=roles, partition=partition,
        provenance=list(ex.provenance.values()), benchmarks=benchmarks, rtc=rtc_asset, mae_sai=mae_asset,
        geography=geography, visuals=visuals,
        sources=source_catalog(summary["attribution"]), assumptions=summary["assumptions"],
        limitations=[
            "Water labels include permanent water; this is not flood-only accuracy.",
            "Three test events do not establish confidence intervals or statistical significance.",
            "Context scores use 100 supported chips / 24,452,094 pixels; SAR uses 111 / 27,693,531.",
            "Eleven Australian context chips have no valid JRC occurrence support and remain in inventory.",
            "WorldCover 2021 and JRC 1984-2020 are retrospective context for older benchmark events.",
            "Calibration and abstention do not improve every model, event or metric; retain negative findings.",
            "RTC comparison uses 46 chips from two events; 65 Australian chips have no matched pre image.",
            "GRD-to-RTC transfer and the change-ramp versus all-water target mismatch limit comparisons.",
            "No qualified Thai reference, Thai accuracy, operational use or FPPS integration is established.",
            "Map coordinates are frozen event bounding-box centres, not independently verified flood centroids.",
            "Full data, model binaries and raster products stay local; web downloads are JSON evidence projections.",
        ], findings=summary["observed_findings"],
        downloads=[asset for asset in ex.assets if "/downloads/" in asset["href"]],
    )
    summary_asset = ex.asset("summary.json", study, "Study summary")
    manifest = envelope("manifest", source_timestamp=study["source_timestamp"],
                        summary=summary_asset, assets=ex.assets.copy())
    ex.files["manifest.json"] = encoded(manifest)
    write_release(ex.files, output)
    return {"study_id": STUDY, "revision": REVISION, "files": len(ex.files),
            "bytes": sum(map(len, ex.files.values())),
            "manifest_sha256": digest(ex.files["manifest.json"])}


def write_release(files: dict[str, bytes], output: Path) -> None:
    """Write a new release or preserve identical bytes; reject conflicting revisions."""
    output = output.resolve()
    # Validate all bytes before touching the destination; never silently revise r1.
    for name, body in files.items():
        destination = output / name
        if not destination.resolve().is_relative_to(output):
            raise ValueError("Output escapes release directory")
        if destination.exists() and destination.read_bytes() != body:
            raise ValueError(f"Immutable revision already contains different bytes: {name}")
    for name, body in files.items():
        destination = output / name
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix(destination.suffix + ".partial")
            temporary.write_bytes(body)
            temporary.replace(destination)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export_study(args.experiment_root.resolve(), args.output.resolve())))


if __name__ == "__main__":
    main()
