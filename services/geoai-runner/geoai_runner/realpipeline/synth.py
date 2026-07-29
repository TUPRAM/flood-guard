"""Deterministic synthetic Mae Sai-like scene for GeoAI pipeline validation.

This module procedurally generates a *coherent* georeferenced scene so that
every downstream model (SAR change detection, U-Net water segmentation, flood
susceptibility regression, building extraction) describes the same physical
place and overlays meaningfully.

Everything is seeded and reproducible. The scene is loosely modelled on the
Mae Sai valley (Chiang Rai, Thailand): a sinuous river in a low valley with
built-up parcels, some of which sit inside the floodplain. It is *not* real
imagery; it is a physically-structured stand-in used to prove the pipeline runs
end to end. See :mod:`geoai_runner.realpipeline` for the honesty boundary.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Approximate Mae Sai anchor (WGS84). The scene is a small ~3 km window.
SCENE_LON_LEFT = 99.865
SCENE_LAT_TOP = 20.440
SCENE_RES_DEG = 0.00012  # ~13 m/pixel at this latitude
SCENE_SIZE = 256
SCENE_CRS = "EPSG:4326"
SCENE_SEED = 20240915  # Mae Sai flood peak date as a seed

S2_BAND_NAMES = ("B2_blue", "B3_green", "B4_red", "B8_nir", "B11_swir1", "B12_swir2")


@dataclass(frozen=True)
class SceneGrid:
    """Georeferencing metadata shared by every raster in the scene."""

    size: int
    res_deg: float
    lon_left: float
    lat_top: float
    crs: str

    @property
    def transform(self):  # -> affine.Affine
        from affine import Affine

        return Affine.translation(self.lon_left, self.lat_top) * Affine.scale(
            self.res_deg, -self.res_deg
        )

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        right = self.lon_left + self.res_deg * self.size
        bottom = self.lat_top - self.res_deg * self.size
        return (self.lon_left, bottom, right, self.lat_top)


def default_grid() -> SceneGrid:
    """Return the standard scene grid used across the pipeline."""

    return SceneGrid(
        size=SCENE_SIZE,
        res_deg=SCENE_RES_DEG,
        lon_left=SCENE_LON_LEFT,
        lat_top=SCENE_LAT_TOP,
        crs=SCENE_CRS,
    )


@dataclass
class SyntheticScene:
    """Container for every array layer in the synthetic scene."""

    grid: SceneGrid
    dem: np.ndarray
    hand: np.ndarray
    slope: np.ndarray
    dist_to_river: np.ndarray
    twi: np.ndarray
    permanent_water: np.ndarray
    flood_reference: np.ndarray  # ground-truth flood extent (flood OR nothing)
    water_reference: np.ndarray  # permanent water OR flood (segmentation target)
    sar_pre_vv: np.ndarray
    sar_pre_vh: np.ndarray
    sar_post_vv: np.ndarray
    sar_post_vh: np.ndarray
    s2: np.ndarray  # (6, H, W) reflectance 0..1 post-event
    buildings: np.ndarray  # uint8 footprint mask
    building_boxes: tuple[tuple[float, float, float, float], ...]  # lon/lat boxes


def build_scene(grid: SceneGrid | None = None, seed: int = SCENE_SEED) -> SyntheticScene:
    """Build the full coherent synthetic scene as numpy arrays."""

    grid = grid or default_grid()
    n = grid.size
    rng = np.random.default_rng(seed)
    rows, cols = np.mgrid[0:n, 0:n].astype("float64")

    # --- River channel: a sinuous low drainage line down the scene ----------
    river_center = n / 2 + 46.0 * np.sin(rows / 34.0) + 12.0 * np.sin(rows / 9.0)
    river_offset = cols - river_center
    river_halfwidth = 4.5 + 1.5 * np.sin(rows / 20.0)
    permanent_water = (np.abs(river_offset) <= river_halfwidth).astype("uint8")
    dist_to_river = np.abs(river_offset)  # pixels; monotone across the valley

    # --- Terrain: valley rising away from the river, plus hills on edges ----
    valley = 0.9 * dist_to_river + 0.004 * dist_to_river**2
    regional = 0.05 * rows  # gentle regional tilt downstream
    hills = 40.0 * np.exp(-((cols - 18) ** 2) / (2 * 22.0**2)) + 55.0 * np.exp(
        -((cols - (n - 20)) ** 2) / (2 * 26.0**2)
    )
    micro = _smoothed_noise(rng, n, scale=6) * 6.0
    dem = 360.0 + valley + regional + hills + micro
    dem = dem - dem.min() + 360.0  # keep realistic Mae Sai valley elevations

    # --- HAND: height above the nearest drainage (per-row river elevation) --
    river_elev_per_row = np.array(
        [
            dem[r, permanent_water[r].astype(bool)].min()
            if permanent_water[r].any()
            else dem[r].min()
            for r in range(n)
        ]
    )
    hand = np.clip(dem - river_elev_per_row[:, None], 0.0, None)

    # --- Slope (degrees) from DEM gradient -----------------------------------
    gy, gx = np.gradient(dem, grid.res_deg * 111000.0)  # metres per pixel approx
    slope = np.degrees(np.arctan(np.sqrt(gx**2 + gy**2)))

    # --- Topographic Wetness Index: ln(a / tan(beta)) approximation ----------
    upslope_proxy = (n - dist_to_river) + 1.0
    twi = np.log(upslope_proxy / (np.tan(np.radians(slope)) + 0.02))

    # --- Flood reference (post-event ground truth) ---------------------------
    # Water collects where HAND is low; a major monsoon flood (e.g. Mae Sai
    # Sep-2024) spreads well beyond the channel across the valley floor.
    flood_susceptibility_true = 1.0 / (1.0 + np.exp((hand - 13.0) / 2.4))
    flood_noise = _smoothed_noise(rng, n, scale=5)
    flood_reference = (
        (flood_susceptibility_true + 0.12 * flood_noise > 0.5) & (dist_to_river < 150)
    ).astype("uint8")
    flood_reference = np.maximum(flood_reference, permanent_water)
    water_reference = flood_reference.copy()  # water = permanent OR flood

    # --- SAR backscatter (linear amplitude); water is specular (low) ---------
    sar_pre_vv, sar_pre_vh = _sar_pair(rng, permanent_water, base_land=0.16)
    sar_post_vv, sar_post_vh = _sar_pair(rng, flood_reference, base_land=0.16)

    # --- Sentinel-2 6-band post-event reflectance ---------------------------
    s2 = _sentinel2_stack(rng, n, water_reference)

    # --- Buildings: a riverside town in the floodplain + a safe hillside -----
    buildings, boxes = _buildings(rng, grid, hand, dist_to_river)
    # Impervious rooftops brighten S2 visible/SWIR
    for b in range(3):
        s2[b][buildings.astype(bool)] = np.clip(s2[b][buildings.astype(bool)] + 0.22, 0, 1)
    s2[4][buildings.astype(bool)] = np.clip(s2[4][buildings.astype(bool)] + 0.20, 0, 1)

    return SyntheticScene(
        grid=grid,
        dem=dem.astype("float32"),
        hand=hand.astype("float32"),
        slope=slope.astype("float32"),
        dist_to_river=(dist_to_river * grid.res_deg * 111000.0).astype("float32"),
        twi=twi.astype("float32"),
        permanent_water=permanent_water,
        flood_reference=flood_reference,
        water_reference=water_reference,
        sar_pre_vv=sar_pre_vv,
        sar_pre_vh=sar_pre_vh,
        sar_post_vv=sar_post_vv,
        sar_post_vh=sar_post_vh,
        s2=s2.astype("float32"),
        buildings=buildings,
        building_boxes=boxes,
    )


def _sar_pair(
    rng: np.random.Generator, water_mask: np.ndarray, base_land: float
) -> tuple[np.ndarray, np.ndarray]:
    """Return (VV, VH) linear amplitude arrays with speckle; water is dark."""

    n = water_mask.shape[0]
    vv = np.full((n, n), base_land, dtype="float32")
    vh = np.full((n, n), base_land * 0.45, dtype="float32")
    vv += 0.03 * _smoothed_noise(rng, n, scale=8)
    vh += 0.015 * _smoothed_noise(rng, n, scale=8)
    water = water_mask.astype(bool)
    vv[water] = 0.035
    vh[water] = 0.012
    # Multiplicative speckle (Gamma) is the defining SAR noise characteristic.
    looks = 6.0
    vv = vv * rng.gamma(looks, 1.0 / looks, size=vv.shape).astype("float32")
    vh = vh * rng.gamma(looks, 1.0 / looks, size=vh.shape).astype("float32")
    return np.clip(vv, 1e-4, None), np.clip(vh, 1e-4, None)


def _sentinel2_stack(rng: np.random.Generator, n: int, water_mask: np.ndarray) -> np.ndarray:
    """Return a (6, H, W) Sentinel-2 reflectance stack with a water signature."""

    water = water_mask.astype(bool)
    # Vegetated / bare land baseline (B2,B3,B4,B8,B11,B12).
    land = np.array([0.06, 0.09, 0.11, 0.34, 0.27, 0.18])
    # Turbid flood water: low NIR/SWIR, slightly raised green (sediment).
    wat = np.array([0.07, 0.10, 0.09, 0.05, 0.04, 0.03])
    stack = np.empty((6, n, n), dtype="float32")
    for b in range(6):
        layer = np.full((n, n), land[b], dtype="float32")
        layer += 0.03 * _smoothed_noise(rng, n, scale=7)
        layer[water] = wat[b] + 0.01 * rng.standard_normal(int(water.sum())).astype("float32")
        stack[b] = np.clip(layer, 0.0, 1.0)
    return stack


def _buildings(
    rng: np.random.Generator,
    grid: SceneGrid,
    hand: np.ndarray,
    dist_to_river: np.ndarray,
) -> tuple[np.ndarray, tuple[tuple[float, float, float, float], ...]]:
    """Place rectangular parcels; return raster mask and lon/lat bounding boxes.

    Roughly half the parcels form a riverside "town" in the low floodplain
    (HAND < 12 m, off-channel) -- these become flood-exposed. The rest sit on
    safer higher ground, so the scene contains both at-risk and safe built-up
    areas, producing a differentiated priority ranking.
    """

    n = grid.size
    mask = np.zeros((n, n), dtype="uint8")
    boxes: list[tuple[float, float, float, float]] = []
    transform = grid.transform
    floodplain = (hand < 12.0) & (dist_to_river >= 5) & (dist_to_river < 70)
    higher = (hand >= 12.0) & (hand < 120.0)
    floodplain_cells = np.argwhere(floodplain)
    higher_cells = np.argwhere(higher)

    def _place(cells: np.ndarray, n_parcels: int) -> None:
        placed = attempts = 0
        while placed < n_parcels and attempts < n_parcels * 60 and len(cells):
            attempts += 1
            r, c = cells[rng.integers(0, len(cells))]
            r = int(min(max(r, 3), n - 8))
            c = int(min(max(c, 3), n - 9))
            h = int(rng.integers(3, 7))
            w = int(rng.integers(3, 8))
            block = mask[r : r + h, c : c + w]
            if block.size == 0 or block.any():
                continue
            mask[r : r + h, c : c + w] = 1
            left, top = transform * (c, r)
            right, bottom = transform * (c + w, r + h)
            boxes.append((min(left, right), min(top, bottom), max(left, right), max(top, bottom)))
            placed += 1

    _place(floodplain_cells, 26)  # riverside town (flood-exposed)
    _place(higher_cells, 22)  # hillside (safer)
    return mask, tuple(boxes)


def _smoothed_noise(rng: np.random.Generator, n: int, scale: int) -> np.ndarray:
    """Cheap smoothed noise field in roughly [-1, 1] without SciPy."""

    coarse = rng.standard_normal((max(2, n // scale), max(2, n // scale)))
    # Bilinear upsample via numpy repeat + averaging passes.
    up = np.kron(coarse, np.ones((scale, scale)))
    up = up[:n, :n]
    if up.shape != (n, n):
        pad = np.zeros((n, n))
        pad[: up.shape[0], : up.shape[1]] = up
        up = pad
    for _ in range(2):
        up = (
            up + np.roll(up, 1, 0) + np.roll(up, -1, 0) + np.roll(up, 1, 1) + np.roll(up, -1, 1)
        ) / 5.0
    std = up.std()
    return (up / std if std > 0 else up).astype("float32")


def subdistrict_features(grid: SceneGrid) -> list[dict]:
    """Return synthetic ADM-like reporting polygons covering the scene.

    Four quadrants, so units genuinely differ in flood exposure: the river
    meanders through the centre, so the two central-valley quadrants carry more
    inundation than the hillside quadrants -- realistic reporting geometry that
    produces a differentiated priority ranking.
    """

    left, bottom, right, top = grid.bounds
    midx = (left + right) / 2.0
    midy = (bottom + top) / 2.0
    quads = [
        ("TH-SYN-01", "Mae Sai (synthetic)", left, midx, midy, top),
        ("TH-SYN-02", "Wiang Phang Kham (synthetic)", midx, right, midy, top),
        ("TH-SYN-03", "Ko Chang (synthetic)", left, midx, bottom, midy),
        ("TH-SYN-04", "Ban Sai Lom (synthetic)", midx, right, bottom, midy),
    ]
    features = []
    for sid, name, x0, x1, y0, y1 in quads:
        ring = [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]
        features.append(
            {
                "type": "Feature",
                "properties": {"subdistrict_id": sid, "subdistrict_name": name},
                "geometry": {"type": "Polygon", "coordinates": [ring]},
            }
        )
    return features
