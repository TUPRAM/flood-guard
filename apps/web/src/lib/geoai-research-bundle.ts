/** Historical experiment records must never be presented as accepted decisions. */
export interface GeoaiResearchBundle {
  data_mode: string;
  study_area: string;
  generated_at: string;
  official_warning: false;
  evidence_tier: "candidate";
  can_feed_decision_layer: false;
  aggregation_status: "report_only";
  sources: Record<string, string>;
  headline: {
    sar_flood_pct: number;
    sar_pre: string;
    sar_post: string;
    unet_iou: number | null;
    unet_f1: number | null;
    unet_metric_role?: string;
    susc_auc: number;
    susc_auc_jrc: number;
    buildings: number;
    exposed: number;
  };
  components: { letter: string; name: string; book: string; metric: string; detail: string; input: string; output: string }[];
  additional_methods?: { letter: string; name: string; book: string; metric: string; detail: string; image: string | null; narratives?: Record<string, Record<string, string>> }[];
  subdistricts: { id: string; name: string; flood_likelihood: number; exposure: number; fpps: number; action: string; confidence: string }[];
  limitations: string[];
}

const record = (v: unknown): v is Record<string, unknown> => v !== null && typeof v === "object" && !Array.isArray(v);
const text = (v: unknown): v is string => typeof v === "string" && v.length > 0;
const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const stringMap = (v: unknown) => record(v) && Object.values(v).every(text);
const image = (v: unknown) => text(v) && /^\/geoai\/[a-zA-Z0-9_-]+\.(png|jpe?g|webp)$/.test(v);
const method = (v: unknown): v is Record<string, unknown> => record(v) && ["letter", "name", "book", "metric", "detail"].every((key) => text(v[key]));

/** Reject missing governance assertions or malformed display data; do not infer eligibility. */
export function parseGeoaiResearchBundle(value: unknown): GeoaiResearchBundle {
  const fail = () => { throw new Error("Archived research bundle has invalid provenance or display fields."); };
  if (!record(value) || !record(value.headline)) return fail();
  const headline = value.headline;
  if (value.official_warning !== false || value.evidence_tier !== "candidate"
    || value.can_feed_decision_layer !== false || value.aggregation_status !== "report_only"
    || !["data_mode", "study_area", "generated_at"].every((key) => text(value[key]))
    || !Number.isFinite(Date.parse(String(value.generated_at))) || !stringMap(value.sources)
    || !["sar_flood_pct", "susc_auc", "susc_auc_jrc", "buildings", "exposed"].every((key) => finite(headline[key]))
    || !["sar_pre", "sar_post"].every((key) => text(headline[key]))
    || !["unet_iou", "unet_f1"].every((key) => headline[key] === null || finite(headline[key]))
    || !(headline.unet_metric_role === undefined || text(headline.unet_metric_role))
    || !Array.isArray(value.components) || !value.components.every((row) => method(row) && image(row.input) && image(row.output))
    || !(value.additional_methods === undefined || (Array.isArray(value.additional_methods) && value.additional_methods.every((row) => method(row) && (row.image === null || image(row.image)) && (row.narratives === undefined || (record(row.narratives) && Object.values(row.narratives).every(stringMap))))))
    || !Array.isArray(value.subdistricts) || !value.subdistricts.every((row) => record(row)
      && ["id", "name", "confidence"].every((key) => text(row[key]))
      && ["flood_likelihood", "exposure", "fpps"].every((key) => finite(row[key]) && row[key] >= 0 && row[key] <= 100)
      && text(row.action) && /^[A-E]$/.test(row.action))
    || !Array.isArray(value.limitations) || !value.limitations.every(text)) return fail();
  return value as unknown as GeoaiResearchBundle;
}
