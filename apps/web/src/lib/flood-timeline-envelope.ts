/**
 * The 2024 season envelope of the Mae Sai replay: UNOSAT and GISTDA product 4009 (accumulated water, August to
 * October 2024) shown as a scenario layer (lane SCN-ENV).
 *
 * The envelope is water mapped at some time in the season, with no date per patch. It is never an observation for a
 * replay day: its toggle is independent of the day slider, it is not among the day observations, and nothing here
 * takes a replay time. Setting the modelled water beside it is a plausibility comparison, not a validation.
 *
 * Its files (a 1-bit raster, a statistics file and a licence notice) are derived from the product and ship under
 * CC BY-SA 4.0 in a folder of their own. Whenever the layer is visible, the map credit adds the product's holders and
 * the licence, and an exported PNG or video carries the product's full credit, the licence with its address and a
 * note of what FloodGuard changed (`envelopeExportCredit`). If the label, the caption, the standard sentence (the
 * extent is preliminary and FloodGuard did not validate it), the credit or the licence cannot be shown, the layer does
 * not ship: `shippableEnvelope` and `parseSeasonEnvelopeDocument` refuse it.
 *
 * Pure logic only; no DOM access in this module.
 */

import {
  SEASON_ENVELOPE_ROLE,
  type HashedAsset,
  type Language,
  type Localized,
  type PngRaster,
  type Rgba,
  type SeasonEnvelopeBlock,
  type TimelineManifest,
} from "./flood-timeline";

export const SEASON_ENVELOPE_LANE = "SCN-ENV";
/** The only licence a file derived from product 4009 may ship under (owner decision D2). */
export const SEASON_ENVELOPE_LICENCE = "CC BY-SA 4.0";
/** What the chip must begin with: the layer is a scenario, and says so before anything else. */
export const SEASON_ENVELOPE_CHIP_PREFIX = "Scenario (SCN-ENV)";

/** Overlap of the modelled water and the envelope inside one area (`floodguard.season_envelope.mask_agreement`). */
export interface EnvelopeAgreement {
  model_km2: number;
  envelope_km2: number;
  overlap_km2: number;
  union_km2: number;
  model_only_km2: number;
  envelope_only_km2: number;
  /** Overlap divided by union; null without a union. */
  agreement_iou: number | null;
  /** Share of the modelled water that lies inside the envelope. */
  containment_model_in_envelope: number | null;
  /** Share of the envelope that the modelled water reaches. */
  containment_envelope_in_model: number | null;
}
export interface EnvelopeDistrictRow extends EnvelopeAgreement { id: string; model_stage_m: number; model_extent: string }
export interface EnvelopeTambonRow extends EnvelopeAgreement { tambon_id: string }

/** `unosat4009/envelope.json`: what the layer is, its licence, credit and change notice, its areas and the comparison. */
/** An input besides the product whose figures the statistics file holds; it keeps its own licence and credit. */
export interface EnvelopeOtherInput { id: string; name: string; licence: string; attribution: string; used_for: string; timestamp?: string }

export interface SeasonEnvelopeDocument {
  schema: string;
  id: string;
  generated_at: string;
  lane: "SCN-ENV";
  evidence_tier: string;
  season_window: string;
  source_timestamp: string;
  not_an_observation_for_any_replay_day: true;
  label: string;
  caption: string;
  standard_sentence: string;
  source: { name: string; product_url: string; dataset_url: string; layer: string; field_validation: number };
  licence: { name: string; full_name: string; url: string; legal_code_url: string };
  credit: string;
  map_credit: string;
  change_notice: string;
  /** Terrain model, population grid and boundaries: the inputs besides the product, each with its licence and credit. */
  other_inputs: EnvelopeOtherInput[];
  other_inputs_note?: string;
  changes: { repair: { parts_repaired: number; source_parts: number; source_parts_invalid: number; parts_meeting_district: number } };
  raster: { file: string; sha256: string; bytes: number; width: number; height: number; bit_depth: number; bounds: [[number, number], [number, number]] };
  area: {
    district_km2: number;
    on_mapped_channels_km2: number;
    by_tambon: Record<string, { envelope_km2: number; tambon_km2: number; share_of_tambon: number | null }>;
  };
  comparison: {
    role: typeof SEASON_ENVELOPE_ROLE;
    title: string;
    use: string;
    rule: string;
    change_notice: string;
    district: EnvelopeDistrictRow[];
    by_tambon_stage: string;
    by_tambon: EnvelopeTambonRow[];
    disagreement: { minimum_km2: number; envelope_water_the_model_lacks: string[]; modelled_water_outside_the_envelope: string[] };
    low_confidence: {
      low_confidence_model_km2: number;
      other_model_km2: number;
      share_inside_envelope_low_confidence: number | null;
      share_inside_envelope_other: number | null;
    };
    /** Null figures with the reason: no land-cover map is among the replay's inputs. */
    land_cover: { computed: boolean; reason: string };
    /**
     * Residents inside the envelope by two rules, each named: `residents_in_envelope` counts whole WorldPop cells
     * (about 100 m) by their centre, the exposure definition stated for the planning overlay;
     * `residents_in_envelope_replay_rule` counts like the replay's residents in water, so it is the one to set beside
     * `model_residents_in_water`.
     */
    residents: {
      residents_in_envelope: number; rule: string; residents_in_envelope_replay_rule: number; replay_rule: string;
      model_residents_in_water: number; source: string; scope: string; rules_note?: string;
    };
    tuning: { relation: string; statement: string; rule: string };
  };
  confidence: string;
  confidence_reason: string;
  assumptions: string[];
  limitations: string[];
  official_warning: false;
  operational_status: "non_operational";
  can_feed_decision_layer: false;
}

export class SeasonEnvelopeError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SeasonEnvelopeError";
  }
}

const isRecord = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === "object" && !Array.isArray(value);
const text = (value: unknown): value is string => typeof value === "string" && value.trim().length > 0;
const SHA256 = /^[a-f0-9]{64}$/;
const fileReference = (value: unknown): value is HashedAsset => isRecord(value) && text(value.href) && typeof value.sha256 === "string"
  && SHA256.test(value.sha256) && typeof value.bytes === "number" && value.bytes > 0;
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const share = (value: unknown): boolean => value === null || (finite(value) && value >= 0 && value <= 1);
const texts = (value: unknown): value is string[] => Array.isArray(value) && value.every((item) => typeof item === "string");

/**
 * The holders a credit names first: its text before the first comma ("UNOSAT and GISTDA, FL20240912THA, UNOSAT
 * product 4009" gives "UNOSAT and GISTDA"). A short credit must name them, never the licence alone.
 */
export const creditHolders = (credit: string): string => credit.split(",", 1)[0].trim();
/** What the standard sentence of a season envelope must say, whatever else it says. */
export const SEASON_ENVELOPE_NOT_VALIDATED = "did not validate";

/**
 * The manifest's season envelope when everything it needs to be shown is there: the scenario lane, the chip and the
 * caption (which must say that it is not an observation for any replay day), the standard sentence (which must say
 * that FloodGuard did not validate the extent), the licence, the credit, a map credit that names the licence and the
 * holders the credit begins with, and the three files. Otherwise null: without a label, the standard sentence or a
 * credit that names somebody the layer does not ship, so the page shows no toggle, no layer and no comparison.
 */
export function shippableEnvelope(manifest: Pick<TimelineManifest, "season_envelope"> | null | undefined): SeasonEnvelopeBlock | null {
  const block: unknown = manifest?.season_envelope;
  if (!isRecord(block)) return null;
  const files = block.files;
  const ok = block.lane === SEASON_ENVELOPE_LANE && block.shown === true && block.day_independent === true
    && text(block.label) && block.label.startsWith(SEASON_ENVELOPE_CHIP_PREFIX)
    && text(block.caption) && block.caption.includes("not an observation for any replay day")
    && text(block.standard_sentence) && block.standard_sentence.includes(SEASON_ENVELOPE_NOT_VALIDATED)
    && block.licence === SEASON_ENVELOPE_LICENCE && text(block.licence_url)
    && text(block.credit) && text(block.map_credit) && block.map_credit.includes(SEASON_ENVELOPE_LICENCE)
    && creditHolders(block.credit).length > 0 && block.map_credit.includes(creditHolders(block.credit))
    && isRecord(files) && fileReference(files.raster) && fileReference(files.statistics) && fileReference(files.licence);
  return ok ? (block as unknown as SeasonEnvelopeBlock) : null;
}

/**
 * Read a fetched `envelope.json` for the manifest's envelope `block`. It refuses, with a `SeasonEnvelopeError`, a
 * document that is not a scenario envelope, that does not say it is no observation for a replay day, whose licence,
 * credit or map credit differ from the manifest's, that lacks its change notice or its other inputs, or whose
 * comparison is not the plausibility comparison. It also refuses a document that lacks any figure or sentence the
 * page reads (a district or subdistrict row without its areas and ratios, the two lists of largest differences, the
 * low-confidence shares, the two counts of residents with their rules, the land-cover note, the tuning rule, the
 * limits): the page then says that the comparison is not shown, instead of failing while it draws it. A refused
 * document means the layer and the comparison are not shown.
 */
export function parseSeasonEnvelopeDocument(value: unknown, block: SeasonEnvelopeBlock): SeasonEnvelopeDocument {
  if (!isRecord(value)) throw new SeasonEnvelopeError("The season-envelope file is not an object.");
  if (value.lane !== SEASON_ENVELOPE_LANE || value.not_an_observation_for_any_replay_day !== true) {
    throw new SeasonEnvelopeError("The season-envelope file must be a scenario envelope and say that it is no observation for a replay day.");
  }
  const licence = value.licence;
  if (!isRecord(licence) || licence.name !== SEASON_ENVELOPE_LICENCE || licence.name !== block.licence || !text(licence.url)) {
    throw new SeasonEnvelopeError("The season-envelope file must carry the CC BY-SA 4.0 licence the manifest names.");
  }
  if (value.credit !== block.credit || value.map_credit !== block.map_credit) throw new SeasonEnvelopeError("The season-envelope file and the manifest give different credits.");
  if (!text(value.change_notice) || !text(value.label) || !text(value.caption)) throw new SeasonEnvelopeError("The season-envelope file lacks its label, caption or change notice.");
  if (value.official_warning !== false || value.operational_status !== "non_operational" || value.can_feed_decision_layer !== false) {
    throw new SeasonEnvelopeError("The season-envelope file must be non-operational and not an official warning.");
  }
  const raster = value.raster;
  if (!isRecord(raster) || raster.sha256 !== block.files.raster.sha256 || typeof raster.width !== "number" || typeof raster.height !== "number") {
    throw new SeasonEnvelopeError("The season-envelope file describes another raster than the manifest names.");
  }
  const comparison = value.comparison;
  if (!isRecord(comparison) || comparison.role !== SEASON_ENVELOPE_ROLE || !text(comparison.use) || !comparison.use.includes("not a validation")
    || !Array.isArray(comparison.district) || comparison.district.length === 0 || !Array.isArray(comparison.by_tambon)) {
    throw new SeasonEnvelopeError("The season-envelope comparison must be a plausibility comparison with its district rows.");
  }
  if (!text(value.confidence) || !text(value.confidence_reason) || !text(value.source_timestamp) || !text(value.generated_at)
    || !texts(value.assumptions) || value.assumptions.length === 0 || !texts(value.limitations)) {
    throw new SeasonEnvelopeError("The season-envelope file lacks its confidence, timestamps, assumptions or limits.");
  }
  const inputs = value.other_inputs;
  if (!Array.isArray(inputs) || inputs.length === 0
    || !inputs.every((item) => isRecord(item) && text(item.id) && text(item.name) && text(item.licence) && text(item.attribution) && text(item.used_for))) {
    throw new SeasonEnvelopeError("The season-envelope file must list its other inputs, each with its licence and its credit.");
  }
  // Every figure and sentence the comparison group prints, so that a file of another shape gives "not shown", never a crash.
  const agreement = (row: unknown): row is Record<string, unknown> => isRecord(row)
    && ["model_km2", "envelope_km2", "overlap_km2", "model_only_km2", "envelope_only_km2"].every((key) => finite(row[key]))
    && ["agreement_iou", "containment_model_in_envelope", "containment_envelope_in_model"].every((key) => share(row[key]));
  if (!comparison.district.every((row) => agreement(row) && text(row.id) && text(row.model_extent) && finite(row.model_stage_m))
    || !comparison.by_tambon.every((row) => agreement(row) && text(row.tambon_id))) {
    throw new SeasonEnvelopeError("A row of the season-envelope comparison lacks its areas, its ratios or its name.");
  }
  const { disagreement, low_confidence: low, residents, land_cover: landCover, tuning } = comparison;
  if (!isRecord(disagreement) || !texts(disagreement.envelope_water_the_model_lacks) || !texts(disagreement.modelled_water_outside_the_envelope)) {
    throw new SeasonEnvelopeError("The season-envelope comparison lacks its lists of largest differences.");
  }
  if (!isRecord(low) || !share(low.share_inside_envelope_low_confidence) || !share(low.share_inside_envelope_other)) {
    throw new SeasonEnvelopeError("The season-envelope comparison lacks its low-confidence shares.");
  }
  if (!isRecord(residents) || !finite(residents.residents_in_envelope) || !text(residents.rule) || !finite(residents.residents_in_envelope_replay_rule)
    || !text(residents.replay_rule) || !finite(residents.model_residents_in_water)) {
    throw new SeasonEnvelopeError("The season-envelope comparison must give both counts of residents in the envelope, each with its rule, and the model's.");
  }
  if (!isRecord(landCover) || typeof landCover.computed !== "boolean" || (!landCover.computed && !text(landCover.reason))) {
    throw new SeasonEnvelopeError("The season-envelope comparison must say whether the land-cover split was computed, and why not.");
  }
  if (!isRecord(tuning) || !text(tuning.statement) || !text(tuning.rule)) {
    throw new SeasonEnvelopeError("The season-envelope comparison lacks its tuning statement and rule.");
  }
  return value as unknown as SeasonEnvelopeDocument;
}

/**
 * Whether the envelope is drawn: the reader's toggle, once the layer's files have loaded. It takes no replay time on
 * purpose: no day, hour or stage ever selects the layer.
 */
export function seasonEnvelopeDrawn(toggle: boolean, ready: boolean): boolean {
  return toggle && ready;
}

/**
 * The credit the map adds for the envelope: its holders and its licence while the layer is visible, nothing while it
 * is hidden. The caption under the map carries the full credit, the licence link and what FloodGuard changed.
 */
export function envelopeCredit(envelope: Pick<SeasonEnvelopeBlock, "map_credit"> | null | undefined, visible: boolean): string | null {
  return visible && envelope ? envelope.map_credit : null;
}

/** What an exported picture needs of the envelope's block to credit it in full. */
export type EnvelopeExportCredit = Pick<SeasonEnvelopeBlock, "credit" | "licence" | "licence_url">;

/**
 * The credit an exported PNG or video carries for the envelope. The picture leaves the page, so it is an adaptation
 * of the product on its own: it states the product's full credit as the rights record gives it (holders, event code
 * and product number), the licence with its address, and what FloodGuard changed. The credit and the licence stay as
 * published; the change note follows the picture's language. The exports wrap this text, they never cut it.
 */
export function envelopeExportCredit(envelope: EnvelopeExportCredit, language: Language): string {
  const parts = envelopeExportCreditParts(envelope, language);
  return `${parts.published} · ${parts.change}`;
}

/** The two parts of `envelopeExportCredit`: the credit and the licence as published, and the change note in `language`. */
export function envelopeExportCreditParts(envelope: EnvelopeExportCredit, language: Language): { published: string; change: string } {
  const address = envelope.licence_url.replace(/^https?:\/\//, "").replace(/\/$/, "");
  return { published: `${envelope.credit} · ${envelope.licence} (${address})`, change: ENVELOPE_EXPORT_CHANGE[language] };
}

/** Cells of the decoded 1-bit raster that lie inside the envelope (sample at or above 128). */
export function envelopeCells(raster: Pick<PngRaster, "width" | "height" | "channels" | "data">, width: number, height: number): Uint32Array {
  if (raster.width !== width || raster.height !== height) throw new SeasonEnvelopeError("The season-envelope raster is not on the replay's water grid.");
  const { channels, data } = raster;
  const count = width * height;
  let inside = 0;
  for (let cell = 0; cell < count; cell += 1) if (data[cell * channels] >= 128) inside += 1;
  const cells = new Uint32Array(inside);
  let cursor = 0;
  for (let cell = 0; cell < count; cell += 1) if (data[cell * channels] >= 128) cells[cursor++] = cell;
  return cells;
}

/**
 * Colours of the envelope's hatch: a dark stripe with a yellow edge, over a faint yellow wash. The pair stays
 * visible on dark imagery and on a pale basemap alike, and neither colour is used by the water, the roads or the
 * VIIRS classes. The layer is told apart by the hatch, never by colour alone.
 */
export const ENVELOPE_RGBA = {
  dark: [38, 30, 0, 235],
  light: [255, 204, 0, 240],
  wash: [255, 204, 0, 38],
} as const satisfies Record<string, Rgba>;

/** Hatch geometry in raster cells: stripes run "\\" (the low-confidence hatch runs "/"). */
export interface EnvelopeHatch { period: number; dark: number; light: number }

/** Screen pixels per raster cell up to which the hatch keeps its 9 px period; a closer view widens it (see `envelopeHatch`). */
export const ENVELOPE_HATCH_STEADY_SCALE = 2;

/**
 * Hatch for a raster drawn at `screenScale` screen pixels per raster cell. The hatch is painted in whole raster cells
 * (about 15 m), so its width on screen is steady only while a cell is small: up to `ENVELOPE_HATCH_STEADY_SCALE`
 * screen pixels per cell the period stays about 9 px, with a dark stripe of about 2 px and a yellow edge of about
 * 1.5 px. Closer in, a stripe cannot be thinner than one cell and the period cannot be shorter than four cells, so
 * the hatch grows with the zoom (four cells: about 22 px at 5.6 px per cell) and its stripes show the cells' steps.
 * The pattern stays a hatch at every zoom; only its width is not constant.
 */
export function envelopeHatch(screenScale: number): EnvelopeHatch {
  const scale = Number.isFinite(screenScale) && screenScale > 0 ? screenScale : 1;
  const dark = Math.max(1, Math.round(2 / scale));
  const light = Math.max(1, Math.round(1.5 / scale));
  return { period: Math.max(dark + light + 2, Math.round(9 / scale)), dark, light };
}

/** 0 on the dark stripe, 1 on its yellow edge, 2 on the wash between stripes, for the cell at column `x`, row `y`. */
export function envelopeHatchClass(x: number, y: number, hatch: EnvelopeHatch): 0 | 1 | 2 {
  const phase = (((x - y) % hatch.period) + hatch.period) % hatch.period;
  return phase < hatch.dark ? 0 : phase < hatch.dark + hatch.light ? 1 : 2;
}

const pack = ([r, g, b, a]: Rgba, littleEndian: boolean) => (littleEndian
  ? ((a << 24) | (b << 16) | (g << 8) | r) >>> 0
  : ((r << 24) | (g << 16) | (b << 8) | a) >>> 0);

/** Paint the envelope's hatch on its own canvas pixels: every cell of the envelope gets a stripe or the wash. */
export function paintEnvelope(cells: Uint32Array, width: number, pixels: Uint32Array, hatch: EnvelopeHatch, littleEndian = true): void {
  const colours = [pack(ENVELOPE_RGBA.dark, littleEndian), pack(ENVELOPE_RGBA.light, littleEndian), pack(ENVELOPE_RGBA.wash, littleEndian)];
  for (let index = 0; index < cells.length; index += 1) {
    const cell = cells[index];
    const x = cell % width;
    pixels[cell] = colours[envelopeHatchClass(x, (cell - x) / width, hatch)];
  }
}

/** A share between 0 and 1 as a percentage to one decimal ("60.5%"), or a dash when it has no denominator. */
export const envelopeShare = (value: number | null | undefined): string => (value == null ? "–" : `${(value * 100).toFixed(1)}%`);
/** The agreement ratio to two decimals ("0.48"), or a dash when it has no union. */
export const envelopeIou = (value: number | null | undefined): string => (value == null ? "–" : value.toFixed(2));

/** Page wording for the layer that the manifest does not carry: the toggle, the legend entry and the status lines. */
export const ENVELOPE_COPY = {
  toggle: { en: "2024 season envelope (scenario, hatched)", th: "ขอบเขตน้ำตลอดฤดูปี 2567 (2024) (สถานการณ์จำลอง ลายเส้นทแยง)" },
  legendTitle: { en: "Season envelope (scenario)", th: "ขอบเขตน้ำตลอดฤดู (สถานการณ์จำลอง)" },
  legend: {
    en: "Hatched: water mapped at some time from August to October 2024; not an observation for any replay day",
    th: "ลายเส้นทแยง: น้ำที่ทำแผนที่ไว้ในช่วงใดช่วงหนึ่งตั้งแต่สิงหาคมถึงตุลาคม 2567 (2024) ไม่ใช่การสังเกตการณ์ของวันใดในการย้อนดู",
  },
  exportLegend: {
    en: "2024 season envelope (scenario; not an observation for any replay day)",
    th: "ขอบเขตน้ำตลอดฤดูปี 2567 (2024) (สถานการณ์จำลอง ไม่ใช่การสังเกตการณ์ของวันใดในการย้อนดู)",
  },
  loading: { en: "Loading the season envelope…", th: "กำลังโหลดขอบเขตน้ำตลอดฤดู…" },
  failed: {
    en: "The season envelope could not be loaded, so its layer and its comparison are not shown.",
    th: "โหลดขอบเขตน้ำตลอดฤดูไม่สำเร็จ จึงไม่แสดงชั้นข้อมูลและการเทียบของขอบเขตนี้",
  },
  // The statistics loaded and the raster did not: the comparison needs only the statistics, so it stays.
  layerFailed: {
    en: "The season envelope's map layer could not be loaded, so the layer is not shown. Its comparison figures are still shown under “Evidence for this moment”.",
    th: "โหลดชั้นแผนที่ของขอบเขตน้ำตลอดฤดูไม่สำเร็จ จึงไม่แสดงชั้นข้อมูลนี้ ตัวเลขการเทียบยังแสดงอยู่ในหัวข้อ “หลักฐานของช่วงเวลานี้”",
  },
  comparisonFailed: {
    en: "The figures of this comparison are not shown: its statistics file could not be loaded.",
    th: "ไม่แสดงตัวเลขของการเทียบนี้ เนื่องจากโหลดไฟล์สถิติไม่สำเร็จ",
  },
} as const satisfies Record<string, Localized>;

/** What FloodGuard changed, as an exported picture says it after the product's credit and licence. */
export const ENVELOPE_EXPORT_CHANGE: Localized = {
  en: "clipped to Mae Sai district and rasterised by FloodGuard",
  th: "FloodGuard ตัดตามขอบเขตอำเภอแม่สายและแปลงเป็นราสเตอร์",
};

/** Subdistrict names for a list of ids, joined for a sentence ("Ko Chang (11.6 km²), Mae Sai (5.6 km²) and …"). */
export function envelopeDifferenceList(
  ids: readonly string[],
  rows: readonly EnvelopeTambonRow[],
  key: "envelope_only_km2" | "model_only_km2",
  name: (id: string) => string,
  language: Language,
): string {
  const parts = ids.map((id) => {
    const row = rows.find((item) => item.tambon_id === id);
    return `${name(id)} (${row ? row[key].toFixed(1) : "–"} ${language === "th" ? "ตร.กม." : "km²"})`;
  });
  if (parts.length <= 1) return parts.join("");
  return language === "th"
    ? `${parts.slice(0, -1).join(" ")} และ${parts[parts.length - 1]}`
    : `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
}
