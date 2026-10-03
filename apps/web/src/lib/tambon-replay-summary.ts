/**
 * The per-subdistrict figures the replay page derives from its manifest at the modelled peak, in the shape of a record
 * of the export pack's `tambon_replay_summary.json` (roadmap P3-2). Everything here is built from the page's own
 * functions (`districtStats`, `roadState`, `summarizeAccessSets`, `accessSnapshot`, `tambonResidents`,
 * `floodedHomeMask`), so a unit test can show that every record of the download equals what the page shows or would
 * show for that subdistrict. A T1 scenario (model): no priority score and no action class is computed here.
 */

import {
  coverageShare,
  districtStats,
  roadState,
  roundLikePython,
  type FacilityProps,
  type RoadProps,
  type TimelineDay,
  type TimelineManifest,
} from "./flood-timeline";
import {
  accessSnapshot,
  floodedHomeMask,
  planSetId,
  REPORTED_SET_ID,
  summarizeAccessSets,
  tambonResidents,
  type AccessNodes,
} from "./flood-timeline-evacuation";

/** One shelter set counted for one group of residents in one subdistrict at the modelled peak (rounded like the download). */
export interface TambonAccessCount {
  residents: number;
  within_reach_before_flood: number;
  already_out_of_reach_before_flood: number;
  lost_access: number;
  keeping_access: number;
  lost_share_of_within_reach: number | null;
}

export type TambonAccessScope = "all_residents_at_road_nodes" | "residents_whose_homes_flood_at_peak";
export type TambonAccessSet = "reported_2024" | "knee_plan";

/** The figures of one subdistrict at the modelled peak. */
export interface TambonPeakFigures {
  tambon_id: string;
  area_km2: number;
  modelled_share_of_area: number | null;
  modelled_peak_stage_m: number;
  modelled_flooded_km2_at_peak: number;
  modelled_flooded_share_of_subdistrict: number | null;
  modelled_flooded_share_of_district: number | null;
  modelled_residents_in_water_at_peak: number;
  modelled_road_km_impassable_at_peak: number;
  modelled_access_at_peak: Record<TambonAccessSet, Record<TambonAccessScope, TambonAccessCount>>;
}

/** The replay day at the modelled peak: the first day at the highest keyframe stage (12 Sep 2024, 3.5 m, in r4). */
export function peakDay(manifest: Pick<TimelineManifest, "days">): TimelineDay {
  return manifest.days.reduce((best, day) => (day.stage_m > best.stage_m ? day : best), manifest.days[0]);
}

const round = roundLikePython;
const share = (part: number, whole: number, digits = 4): number | null => (whole > 0 ? round(part / whole, digits) : null);

/**
 * Every subdistrict's figures at the modelled peak, in `access.tambons` order, as the page derives them: flooded area
 * and residents in water from the histograms (`districtStats`), impassable road length from the drawn road pieces of
 * the subdistrict (`roadState`), and walking access for the reported 2024 set and the knee plan, counted both ways
 * (all residents at road nodes, and residents whose homes flood at the peak), from the access node file.
 */
export function tambonPeakFigures(
  manifest: TimelineManifest,
  roads: readonly Pick<RoadProps, "h" | "len" | "m" | "k" | "t">[],
  facilities: readonly Pick<FacilityProps, "h" | "m">[],
  nodes: AccessNodes,
): TambonPeakFigures[] {
  const access = manifest.access;
  const shelters = manifest.shelters;
  if (!access || !shelters) throw new Error("The manifest has no access scenario or shelter plan");
  const stage = peakDay(manifest).stage_m;
  const stats = districtStats(manifest, stage, roads, facilities);
  const impassable = new Map<string, number>();
  for (const road of roads) {
    if (!road.m || roadState(road.h, stage, manifest.impassable_depth_m, road.k ?? 1) !== "impassable") continue;
    impassable.set(road.t, (impassable.get(road.t) ?? 0) + road.len);
  }
  const flooded = floodedHomeMask(nodes, shelters.method.peak_stage_m, manifest.hand.step_m, manifest.hand.channel_code, manifest.hand.never_code);
  const scopes: [TambonAccessScope, Uint8Array | null][] = [["all_residents_at_road_nodes", null], ["residents_whose_homes_flood_at_peak", flooded]];
  const sets: [TambonAccessSet, string][] = [["reported_2024", REPORTED_SET_ID], ["knee_plan", planSetId(shelters.knee_k)]];
  const counted = scopes.map(([scope, mask]) => ({
    scope,
    summaries: summarizeAccessSets(nodes, access, mask),
    residents: tambonResidents(nodes, access.tambons.length, mask),
  }));
  return access.tambons.map((id, place) => {
    const coverage = manifest.tambon_coverage?.[id];
    const area = coverage?.total_km2 ?? 0;
    const floodedKm2 = stats.tambon_flooded_km2[id] ?? 0;
    const perSet = Object.fromEntries(sets.map(([label, setId]) => {
      const setIndex = access.sets.indexOf(setId);
      if (setIndex < 0) throw new Error(`The access scenario has no set ${setId}`);
      return [label, Object.fromEntries(counted.map(({ scope, summaries, residents }) => {
        const snapshot = accessSnapshot(summaries[setIndex], shelters.method.peak_stage_m, access.levels);
        const lost = snapshot.lostByTambon[place] ?? 0;
        const never = snapshot.neverByTambon[place] ?? 0;
        const total = residents[place] ?? 0;
        const within = Math.max(0, total - never);
        const withinRounded = round(within, 1);
        return [scope, {
          residents: round(total, 1),
          within_reach_before_flood: withinRounded,
          already_out_of_reach_before_flood: round(never, 1),
          lost_access: round(lost, 1),
          keeping_access: round(Math.max(0, within - lost), 1),
          lost_share_of_within_reach: withinRounded > 0 ? round(lost / within, 4) : null,
        } satisfies TambonAccessCount];
      }))];
    })) as TambonPeakFigures["modelled_access_at_peak"];
    return {
      tambon_id: id,
      area_km2: area,
      modelled_share_of_area: area > 0 ? round(coverageShare(coverage), 4) : null,
      modelled_peak_stage_m: stage,
      modelled_flooded_km2_at_peak: floodedKm2,
      modelled_flooded_share_of_subdistrict: share(floodedKm2, area),
      modelled_flooded_share_of_district: share(floodedKm2, stats.flooded_km2),
      modelled_residents_in_water_at_peak: stats.tambon_people_in_water?.[id] ?? 0,
      modelled_road_km_impassable_at_peak: round((impassable.get(id) ?? 0) / 1000, 2),
      modelled_access_at_peak: perSet,
    };
  });
}
