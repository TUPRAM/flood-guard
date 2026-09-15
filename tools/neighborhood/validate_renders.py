"""Verify rendered camera/water states, native files and browser asset provenance."""

import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[2]
RENDERS = ROOT / "outputs/landing-v2-assets/renders"


def triangle_determinant(triangle: list[list[float]]) -> float:
    """Return the signed double area of three native-image points."""
    a, b, c = triangle
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def affine_point(point: list[float], source: list[list[float]], target: list[list[float]]) -> list[float]:
    """Map a point by the unique affine transform between two triangles."""
    a, b, c = source
    determinant = triangle_determinant(source)
    dx, dy = point[0] - a[0], point[1] - a[1]
    u = (dx * (c[1] - a[1]) - dy * (c[0] - a[0])) / determinant
    v = ((b[0] - a[0]) * dy - (b[1] - a[1]) * dx) / determinant
    return [target[0][axis] + u * (target[1][axis] - target[0][axis])
            + v * (target[2][axis] - target[0][axis]) for axis in range(2)]


def validate_registration(manifest: dict) -> dict:
    """Validate every camera triangle and measure remaining ground/roof parallax."""
    frames = manifest["cameraFrames"]
    assert len(frames) == 16, "All sixteen rendered cameras need registration"
    registration = manifest["cameraRegistration"]
    assert registration["origin"] == "top-left"
    assert registration["space"] == "native-image-pixels"
    assert len(registration["worldTriangle"]) == 3
    assert all(len(point) == 3 and all(math.isfinite(value) for value in point)
               for point in registration["worldTriangle"])
    assert all(point[2] == registration["planeHeight"] for point in registration["worldTriangle"])
    probes = registration["diagnosticProbes"]
    assert sum(probe["kind"] == "ground" for probe in probes) >= 1
    assert sum(probe["kind"] == "roof" for probe in probes) >= 1
    determinants = []
    for index, frame in enumerate(frames):
        triangle = frame["projection"]
        assert len(triangle) == 3, f"Frame {index}: three projected points required"
        assert all(len(point) == 2 and all(math.isfinite(value) for value in point)
                   for point in triangle), f"Frame {index}: finite 2D projections required"
        determinant = triangle_determinant(triangle)
        assert abs(determinant) > 2, f"Frame {index}: nondegenerate registration required"
        determinants.append(determinant)
        assert math.isclose(frame["at"], index / 15, abs_tol=1e-6)
        assert len(frame["projectionDiagnostics"]) == len(probes)
        assert all(len(point) == 2 and all(math.isfinite(value) for value in point)
                   for point in frame["projectionDiagnostics"])
    assert all(value * determinants[0] > 0 for value in determinants), "Camera triangles must retain orientation"
    assert len({tuple(tuple(point) for point in frame["projection"]) for frame in frames}) == 16, "Projected triangles must follow every distinct camera position"
    assert abs(determinants[-1]) > abs(determinants[0]) * 1.1, "Approaching the neighborhood must enlarge the registration triangle"
    residuals = {"ground": {"nativePixels": 0}, "roof": {"nativePixels": 0}}
    for index, (left, right) in enumerate(zip(frames, frames[1:])):
        target = [[(a[axis] + b[axis]) / 2 for axis in range(2)]
                  for a, b in zip(left["projection"], right["projection"])]
        for probe_index, probe in enumerate(probes):
            a = affine_point(left["projectionDiagnostics"][probe_index], left["projection"], target)
            b = affine_point(right["projectionDiagnostics"][probe_index], right["projection"], target)
            error = math.dist(a, b)
            if error > residuals[probe["kind"]]["nativePixels"]:
                residuals[probe["kind"]] = {"nativePixels": round(error, 6), "pair": [index, index + 1], "probe": probe["name"]}
    return {"frames": len(frames), "triangleAreaMinPx2": min(abs(value) / 2 for value in determinants),
            "triangleAreaMaxPx2": max(abs(value) / 2 for value in determinants),
            "midpointAdjacentFrameResidualMax": residuals,
            "measurement": "Separation of corresponding probe points after affine alignment at each adjacent pair midpoint, in native image pixels."}


def main():
    states = {}
    receipts = []
    for name in ["w0", "w1", "w2"] + [f"approach-{index:02}" for index in range(16)]:
        receipt = json.loads((RENDERS / f"{name}.json").read_text(encoding="utf8"))
        image = Image.open(RENDERS / f"{name}.png")
        assert image.size == (receipt["width"], round(receipt["width"] * .75)), name
        assert image.mode == "RGBA", name
        assert all(math.isfinite(value) for value in receipt["camera"]), name
        receipt["sha256"] = hashlib.sha256((RENDERS / f"{name}.png").read_bytes()).hexdigest()
        receipts.append(receipt)
        if name.startswith("w"):
            states[name] = image.convert("RGB")
    assert len({r["sha256"] for r in receipts}) == 19, "Every physical state and camera shot must differ"
    camera_receipts = receipts[3:]
    assert len({tuple(r["camera"]) for r in camera_receipts}) == 16, "Camera must actually approach"
    assert all(abs(r["water"] + .38) < 1e-5 for r in camera_receipts), "Opening stays dry"
    assert camera_receipts[0]["camera"] == [105.0, -136.0, 154.0]
    assert camera_receipts[-1]["camera"] == [69.0, -95.0, 92.0]
    assert all(r["camera"] == camera_receipts[-1]["camera"] for r in receipts[:3]), "Water plates must be registered"
    for receipt, expected in zip(receipts[:3], (-.38, .18, .63)):
        assert abs(receipt["water"] - expected) < 1e-5, "Timeline must not override selected water level"
    difference = ImageChops.difference(states["w0"], states["w2"])
    average_change = sum(ImageStat.Stat(difference).mean) / 3
    assert average_change > 1, "Flood state must visibly change the dry plate"
    manifest = json.loads((ROOT / "apps/web/public/landing/floodguard-v2/scene-manifest.json").read_text(encoding="utf8"))
    registration = validate_registration(manifest)
    anchors = manifest["anchors"]
    for point in [anchors["home"], anchors["clinic"], anchors["report"], *anchors["route"], *anchors["selection"]]:
        assert 0 <= point[0] <= manifest["width"] and 0 <= point[1] <= manifest["height"]
    provenance = json.loads((ROOT / "outputs/landing-v2-assets/asset-provenance.json").read_text(encoding="utf8"))
    for record in provenance["files"]:
        path = ROOT / "apps/web/public" / record["url"].lstrip("/")
        assert path.stat().st_size == record["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]
        assert hashlib.sha256((ROOT / record["source"]).read_bytes()).hexdigest() == record["sourceSha256"]
    report = {"status": "passed", "renderCount": len(receipts), "uniqueCameraPositions": 16,
              "registeredWaterStates": 3, "waterChangeMeanRgb": average_change,
              "runtimeAssetCount": len(provenance["files"]), "runtimeBytes": provenance["runtimeBytes"],
              "cameraRegistration": registration,
              "checks": ["Actual camera movement", "Same camera across water states", "Distinct water levels",
                         "Nonidentical rendered artwork", "RGBA native dimensions", "Anchor bounds", "Finite nondegenerate camera registration triangles", "Exact native and WebP provenance"],
              "renders": receipts}
    path = ROOT / "outputs/landing-v2-assets/render-validation.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    print(json.dumps({key: value for key, value in report.items() if key != "renders"}))


if __name__ == "__main__":
    main()
