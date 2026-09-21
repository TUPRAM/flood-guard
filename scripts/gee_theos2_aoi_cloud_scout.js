/**
 * FloodGuard Thailand - THEOS-2 AOI cloud scout
 *
 * Paste into the Google Earth Engine Code Editor: https://code.earthengine.google.com
 *
 * If you do not have an Earth Engine account, use the Python equivalent instead:
 *   scripts/scout_theos2_aoi_cloud.py
 * It runs against the Microsoft Planetary Computer STAC API with no
 * authentication and writes outputs/theos2_aoi_cloud_scout.csv. This GEE version
 * is kept for interactive map inspection and for anyone already working in EE.
 *
 * Purpose
 *   GISTDA's THEOS-2 ordering portal asks for an AOI, a date range, and a maximum
 *   cloud cover percentage. Guessing those date ranges wastes a request. This
 *   script measures, per AOI, the Sentinel-2 cloud fraction *clipped to the AOI*
 *   for every candidate window, so the requested date ranges can be narrowed to
 *   dates that were demonstrably clear over the target area.
 *
 *   Scene-level CLOUDY_PIXEL_PERCENTAGE is not used, because a 110 km Sentinel-2
 *   tile can be 70% cloudy while a 10 km AOI inside it is clear.
 *
 * What it does NOT do
 *   This is an acquisition-planning aid only. It does not produce a flood mask,
 *   a validation label, a reference mask, or any FloodGuard decision input.
 *   Sentinel-2 is used purely as a cloud-climatology proxy for THEOS-2 tasking.
 *
 * Outputs
 *   1. AOI rectangles drawn on the map.
 *   2. A printed, cloud-sorted candidate list per AOI and window.
 *   3. Optional CSV export of every candidate date (see EXPORT_CSV below).
 *   4. Optional GeoJSON/SHP export of the AOIs themselves.
 */

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

/** Print the N clearest candidate dates per AOI/window. */
var TOP_N = 12;

/** Only list candidates at or below this AOI-clipped cloud fraction (0-1). */
var LIST_CLOUD_MAX = 0.85;

/** Set true to queue a CSV export of all candidates to your Drive. */
var EXPORT_CSV = false;

/** Set true to queue a GeoJSON/SHP export of the AOI rectangles. */
var EXPORT_AOI = false;

// ---------------------------------------------------------------------------
// Areas of interest - identical bounds to resources/aoi/*.geojson
// ---------------------------------------------------------------------------

var AOIS = [
  {
    id: 'AOI-01',
    slug: 'mae_sai_core',
    priority: 'P1',
    event: 'mae_sai_2024',
    label: 'Mae Sai core - town, border crossing, Sai River strip',
    bbox: [99.8384, 20.3705, 99.9441, 20.4563]
  },
  {
    id: 'AOI-02',
    slug: 'mae_sai_district',
    priority: 'P2',
    event: 'mae_sai_2024',
    label: 'Mae Sai district - full 8-subdistrict decision extent',
    bbox: [99.8107, 20.2577, 100.0368, 20.4651]
  },
  {
    id: 'AOI-03',
    slug: 'hat_yai_core',
    priority: 'P1',
    event: 'hat_yai_2025',
    label: 'Hat Yai core - municipality and U Taphao canal reach',
    bbox: [100.43, 6.965, 100.52, 7.055]
  },
  {
    id: 'AOI-04',
    slug: 'hat_yai_basin',
    priority: 'P3',
    event: 'hat_yai_2025',
    label: 'Hat Yai extended - U Taphao basin to Songkhla Lake outlet',
    bbox: [100.38, 6.9, 100.58, 7.12]
  },
  {
    id: 'AOI-05',
    slug: 'chao_phraya_bang_ban_sena',
    priority: 'P2',
    event: 'chao_phraya_2024',
    label: 'Lower Chao Phraya - Bang Ban / Sena, Ayutthaya',
    bbox: [100.4, 14.25, 100.52, 14.37]
  },
  {
    id: 'AOI-06',
    slug: 'chao_phraya_rangsit',
    priority: 'P3',
    event: 'chao_phraya_2024',
    label: 'Greater Bangkok fringe - Rangsit / Thanyaburi, Pathum Thani',
    bbox: [100.6, 13.98, 100.72, 14.08]
  }
];

// ---------------------------------------------------------------------------
// Candidate acquisition windows, keyed by event
// ---------------------------------------------------------------------------

var WINDOWS = {
  mae_sai_2024: [
    { id: 'W1-event', label: 'Flood event window', start: '2024-09-09', end: '2024-09-20', maxCloudPct: 80 },
    { id: 'W2-pre', label: 'Pre-event clear baseline', start: '2024-01-01', end: '2024-02-15', maxCloudPct: 10 },
    { id: 'W3-post', label: 'Post-event clear baseline', start: '2024-11-01', end: '2025-01-31', maxCloudPct: 10 }
  ],
  hat_yai_2025: [
    { id: 'W1-event', label: 'Flood event window', start: '2025-11-19', end: '2025-12-08', maxCloudPct: 80 },
    { id: 'W2-pre', label: 'Pre-event clear baseline', start: '2025-03-01', end: '2025-07-31', maxCloudPct: 10 },
    { id: 'W3-post', label: 'Post-event clear baseline', start: '2026-02-01', end: '2026-06-30', maxCloudPct: 10 }
  ],
  chao_phraya_2024: [
    { id: 'W1-event', label: 'Flood event window 2024', start: '2024-09-25', end: '2024-11-15', maxCloudPct: 80 },
    { id: 'W2-event', label: 'Flood event window 2025', start: '2025-09-20', end: '2025-11-10', maxCloudPct: 80 },
    { id: 'W3-dry', label: 'Dry-season clear baseline', start: '2025-01-01', end: '2025-03-31', maxCloudPct: 10 }
  ]
};

// ---------------------------------------------------------------------------
// Cloud fraction measurement
// ---------------------------------------------------------------------------

/** Sentinel-2 Scene Classification values treated as obscured. */
var SCL_OBSCURED = [3, 8, 9, 10]; // shadow, cloud medium, cloud high, thin cirrus

/**
 * Fraction of an AOI obscured by cloud, cirrus or cloud shadow.
 * Returns an image property `aoiCloudFraction` in [0, 1].
 */
function withAoiCloudFraction(aoiGeom) {
  return function (image) {
    var scl = image.select('SCL');
    var obscured = scl.remap(SCL_OBSCURED, ee.List.repeat(1, SCL_OBSCURED.length), 0);
    var valid = scl.neq(0); // exclude no-data
    var stats = obscured.updateMask(valid).reduceRegion({
      reducer: ee.Reducer.mean(),
      geometry: aoiGeom,
      scale: 60,
      maxPixels: 1e9,
      bestEffort: true
    });
    var coverage = valid.reduceRegion({
      reducer: ee.Reducer.mean(),
      geometry: aoiGeom,
      scale: 60,
      maxPixels: 1e9,
      bestEffort: true
    });
    return image.set({
      aoiCloudFraction: stats.get('remapped'),
      aoiValidCoverage: coverage.get('SCL')
    });
  };
}

/** Candidate dates for one AOI and one window, sorted clearest first. */
function scoutWindow(aoi, aoiGeom, win) {
  var collection = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    .filterBounds(aoiGeom)
    .filterDate(win.start, ee.Date(win.end).advance(1, 'day'))
    .map(withAoiCloudFraction(aoiGeom))
    .filter(ee.Filter.notNull(['aoiCloudFraction']))
    // Drop scenes that only clip a sliver of the AOI.
    .filter(ee.Filter.gte('aoiValidCoverage', 0.2))
    .filter(ee.Filter.lte('aoiCloudFraction', LIST_CLOUD_MAX))
    .sort('aoiCloudFraction');

  return collection.limit(TOP_N).map(function (image) {
    return ee.Feature(null, {
      aoi_id: aoi.id,
      aoi_slug: aoi.slug,
      priority: aoi.priority,
      window_id: win.id,
      window_label: win.label,
      window_start: win.start,
      window_end: win.end,
      requested_max_cloud_pct: win.maxCloudPct,
      date: image.date().format('YYYY-MM-dd'),
      aoi_cloud_pct: ee.Number(image.get('aoiCloudFraction')).multiply(100).round(),
      aoi_valid_coverage_pct: ee.Number(image.get('aoiValidCoverage')).multiply(100).round(),
      scene_cloud_pct: image.get('CLOUDY_PIXEL_PERCENTAGE'),
      s2_product_id: image.get('PRODUCT_ID')
    });
  });
}

// ---------------------------------------------------------------------------
// Run
// ---------------------------------------------------------------------------

var aoiFeatures = [];
var allCandidates = ee.FeatureCollection([]);

AOIS.forEach(function (aoi) {
  var geom = ee.Geometry.Rectangle(aoi.bbox, null, false);
  aoiFeatures.push(
    ee.Feature(geom, {
      aoi_id: aoi.id,
      slug: aoi.slug,
      priority: aoi.priority,
      event: aoi.event,
      label: aoi.label
    })
  );

  Map.addLayer(
    ee.Image().paint(ee.FeatureCollection([ee.Feature(geom)]), 0, 2),
    { palette: aoi.priority === 'P1' ? 'ff3b30' : aoi.priority === 'P2' ? 'ff9500' : '8e8e93' },
    aoi.id + ' ' + aoi.slug + ' (' + aoi.priority + ')',
    aoi.priority === 'P1'
  );

  print('──────── ' + aoi.id + ' ' + aoi.priority + ' · ' + aoi.label);

  WINDOWS[aoi.event].forEach(function (win) {
    var candidates = scoutWindow(aoi, geom, win);
    allCandidates = allCandidates.merge(candidates);
    print(
      aoi.id + ' · ' + win.id + ' · ' + win.label +
        ' · ' + win.start + '→' + win.end +
        ' · requested max cloud ' + win.maxCloudPct + '%',
      candidates
    );
  });
});

var aoiCollection = ee.FeatureCollection(aoiFeatures);
Map.centerObject(aoiCollection, 7);

// ---------------------------------------------------------------------------
// Optional exports
// ---------------------------------------------------------------------------

if (EXPORT_CSV) {
  Export.table.toDrive({
    collection: allCandidates,
    description: 'floodguard_theos2_cloud_candidates_v1',
    fileFormat: 'CSV',
    selectors: [
      'aoi_id', 'aoi_slug', 'priority', 'window_id', 'window_label',
      'window_start', 'window_end', 'requested_max_cloud_pct',
      'date', 'aoi_cloud_pct', 'aoi_valid_coverage_pct',
      'scene_cloud_pct', 's2_product_id'
    ]
  });
}

if (EXPORT_AOI) {
  Export.table.toDrive({
    collection: aoiCollection,
    description: 'floodguard_theos2_aoi_v1',
    fileFormat: 'GeoJSON'
  });
}
