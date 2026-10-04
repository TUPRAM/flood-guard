/**
 * Loads the replay files of the Command exercise replay (Mae Sai, September 2024) in the browser: the manifest, the
 * three vector files, the access node file and the terrain raster the water is painted from. The same r4 files as the
 * Studio replay, read with the same decoders. Also the two optional planning overlays of the table's plan group, the
 * per-subdistrict summary of the export pack, the file of invented exercise items and the raster of the 2024 season
 * envelope. This module uses `fetch` and, as a fallback decoder, a canvas.
 */

import {
  decodePng,
  depthFactorKeys,
  handGridFromRaster,
  hatchStripes,
  inflateZlib,
  lowConfidenceCells,
  parseTimelineManifest,
  TIMELINE_MANIFEST_URL,
  waterCandidates,
  type AreaGeometry,
  type FacilityProps,
  type GeoCollection,
  type LineGeometry,
  type PngRaster,
  type PointGeometry,
  type RoadProps,
  type SeasonEnvelopeBlock,
  type TambonProps,
  type TimelineManifest,
} from "./flood-timeline";
import { EXERCISE_FILE_URL, parseExerciseFile, type ExerciseFile } from "./flood-timeline-command-incidents";
import {
  COMMAND_OVERLAY_HREFS,
  COMMAND_PLANNING_CASES,
  NO_COMMAND_OVERLAYS,
  parsePeakSummary,
  readCommandOverlay,
  type CommandOverlays,
  type CommandPeakRecord,
} from "./flood-timeline-command-table";
import { envelopeCells, shippableEnvelope } from "./flood-timeline-envelope";
import { parseAccessNodes, type AccessNodes } from "./flood-timeline-evacuation";

/** The files the page cannot draw anything without. */
export interface CommandReplayData {
  manifest: TimelineManifest;
  roads: GeoCollection<LineGeometry, RoadProps>;
  facilities: GeoCollection<PointGeometry, FacilityProps>;
  tambons: GeoCollection<AreaGeometry, TambonProps>;
  nodes: AccessNodes;
}

/**
 * The terrain raster as the water painter needs it: codes, optional depth-factor keys (`code | factor << 8`), the
 * cells that can ever be wet, and the low-confidence cells among them with their hatch stripes.
 */
export interface CommandHandRaster {
  codes: Uint8Array;
  factorKeys: Uint16Array | null;
  candidates: Uint32Array;
  lowCells: Uint32Array | null;
  lowStripes: Uint8Array | null;
}

async function fetchJson<T>(href: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(href, { signal });
  if (!response.ok) throw new Error(`${href}: HTTP ${response.status}`);
  return (await response.json()) as T;
}

async function fetchBytes(href: string, signal: AbortSignal): Promise<Uint8Array> {
  const response = await fetch(href, { signal });
  if (!response.ok) throw new Error(`${href}: HTTP ${response.status}`);
  return new Uint8Array(await response.arrayBuffer());
}

/** Fallback decoder for browsers without DecompressionStream; keeps greyscale or RGB according to the file header. */
async function decodeWithCanvas(bytes: Uint8Array): Promise<PngRaster> {
  const colourType = bytes.length > 25 ? bytes[25] : 0;
  const channels = colourType === 0 || colourType === 4 ? 1 : 3;
  const bitmap = await createImageBitmap(new Blob([new Uint8Array(bytes)], { type: "image/png" }), {
    colorSpaceConversion: "none",
    premultiplyAlpha: "none",
  });
  const canvas = document.createElement("canvas");
  canvas.width = bitmap.width;
  canvas.height = bitmap.height;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) throw new Error("Canvas is unavailable");
  context.drawImage(bitmap, 0, 0);
  bitmap.close();
  const rgba = context.getImageData(0, 0, canvas.width, canvas.height).data;
  const count = canvas.width * canvas.height;
  const data = new Uint8Array(count * channels);
  for (let cell = 0; cell < count; cell += 1) {
    for (let channel = 0; channel < channels; channel += 1) data[cell * channels + channel] = rgba[cell * 4 + channel];
  }
  return { width: canvas.width, height: canvas.height, channels, data };
}

/** The manifest, the vector files and the access nodes. Fails as a whole: the figures need every one of them. */
export async function loadCommandReplay(signal: AbortSignal): Promise<CommandReplayData> {
  const manifest = parseTimelineManifest(await fetchJson<unknown>(TIMELINE_MANIFEST_URL, signal));
  if (!manifest.access || !manifest.shelters || !manifest.population) throw new Error("The manifest has no access scenario, shelters or residents");
  const access = manifest.access;
  const [roads, facilities, tambons, nodeBytes] = await Promise.all([
    fetchJson<CommandReplayData["roads"]>(manifest.vectors.roads.href, signal),
    fetchJson<CommandReplayData["facilities"]>(manifest.vectors.facilities.href, signal),
    fetchJson<CommandReplayData["tambons"]>(manifest.vectors.tambons.href, signal),
    fetchBytes(access.nodes.href, signal),
  ]);
  return { manifest, roads, facilities, tambons, nodes: parseAccessNodes(nodeBytes, access) };
}

/**
 * The planning overlays of the two protocol cases the table shows. Each file is optional: a file that is not there,
 * is not JSON or is refused by the reader gives no overlay, and the table then shows its empty state for that case.
 * Neither file exists yet.
 */
export async function loadCommandOverlays(signal: AbortSignal): Promise<CommandOverlays> {
  const overlays: CommandOverlays = { ...NO_COMMAND_OVERLAYS };
  await Promise.all(COMMAND_PLANNING_CASES.map(async (planningCase) => {
    try {
      const response = await fetch(COMMAND_OVERLAY_HREFS[planningCase], { signal });
      if (!response.ok) return;
      overlays[planningCase] = readCommandOverlay(await response.json(), planningCase).overlay;
    } catch {
      // No file, no JSON, or an aborted request: no overlay for this case.
    }
  }));
  return overlays;
}

/** The per-subdistrict summary at the modelled peak, from the export pack the manifest names; empty when it has none. */
export async function loadCommandPeakSummary(manifest: Pick<TimelineManifest, "exports">, signal: AbortSignal): Promise<Map<string, CommandPeakRecord>> {
  const file = manifest.exports?.files.find((item) => item.id === "tambon_replay_summary");
  if (!file) return new Map();
  return parsePeakSummary(await fetchJson<unknown>(file.href, signal));
}

/**
 * The invented items of the exercise. The file is optional: one that is missing, or that the parser refuses (an item
 * without the "EX-" id, a phone number, an urgency that does not follow from its stated facts), shows no item at all.
 */
export async function loadCommandExercise(signal: AbortSignal): Promise<ExerciseFile | null> {
  try {
    const response = await fetch(EXERCISE_FILE_URL, { signal });
    if (!response.ok) return null;
    return parseExerciseFile(await response.json());
  } catch {
    return null;
  }
}

/** The 2024 season envelope for hindsight mode: its block of the manifest (label, credit, licence) and its cells on the water grid. */
export interface CommandEnvelope { block: SeasonEnvelopeBlock; cells: Uint32Array }

/**
 * The season envelope (UNOSAT and GISTDA product 4009), a scenario layer. It is used only when the manifest ships it
 * with its label, caption, licence and credit, and its raster is on the replay's water grid; anything else gives null
 * and hindsight mode then has no envelope.
 */
export async function loadCommandEnvelope(manifest: TimelineManifest, signal: AbortSignal): Promise<CommandEnvelope | null> {
  const block = shippableEnvelope(manifest);
  if (!block) return null;
  try {
    const bytes = await fetchBytes(block.files.raster.href, signal);
    const raster = typeof DecompressionStream === "function" ? await decodePng(bytes, inflateZlib) : await decodeWithCanvas(bytes);
    return { block, cells: envelopeCells(raster, manifest.hand.width, manifest.hand.height) };
  } catch {
    return null;
  }
}

/** The terrain raster of the water layer. It loads on its own: the figures and the roads do not wait for it. */
export async function loadCommandHand(manifest: TimelineManifest, signal: AbortSignal): Promise<CommandHandRaster> {
  const bytes = await fetchBytes(manifest.hand.href, signal);
  const raster = typeof DecompressionStream === "function" ? await decodePng(bytes, inflateZlib) : await decodeWithCanvas(bytes);
  if (raster.width !== manifest.hand.width || raster.height !== manifest.hand.height) throw new Error("HAND raster size mismatch");
  // The B channel is read as a low-confidence flag only when the manifest declares it.
  const grid = handGridFromRaster(raster, manifest.hand.depth_factor_channel, manifest.hand.low_confidence_channel);
  const maxStage = Math.max(...manifest.stage_anchors.map((anchor) => anchor.stage_m));
  const candidates = waterCandidates(grid.codes, maxStage, manifest.hand.step_m);
  const lowCells = grid.lowConfidence ? lowConfidenceCells(grid.codes, grid.lowConfidence, candidates, manifest.hand.channel_code) : null;
  return {
    codes: grid.codes,
    factorKeys: grid.factors ? depthFactorKeys(grid.codes, grid.factors) : null,
    candidates,
    lowCells,
    lowStripes: lowCells ? hatchStripes(lowCells, grid.width) : null,
  };
}
