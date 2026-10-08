import projection from "./policy-case-se1.json";
import type { BilingualText } from "./policy-evidence";

/**
 * The scored case the policy page leads with: case SE1, the 2024 season envelope scenario on the eight Mae Sai
 * tambons. The page prints these figures from a small copy (`policy-case-se1.json`) of the published planning overlay,
 * so they are in the page before JavaScript and the overlay is not added to the page's bundle. A test reads the
 * published overlay through the strict parser and compares every figure, so the copy cannot drift from it.
 */
export type PolicyCaseClass = "A" | "B" | "C" | "D" | "E";

export interface PolicyCaseRow {
  unit_id: string;
  name_en: string;
  name_th: string;
  fpps_0_100: number;
  action_class: PolicyCaseClass;
  action_reason_code: string;
  confidence_class: string;
  confidence_kind: string;
  headline_stability: string;
  components_0_100: Record<string, number>;
  flooded_share_of_land: number;
  residents: number;
  residents_inside_the_layer: number;
  residents_with_hospital_access_before: number;
  residents_losing_hospital_access: number;
  residents_with_a_route_before: number;
  residents_losing_every_route: number;
}

export const POLICY_CASE = projection as Omit<typeof projection, "rows"> & { rows: PolicyCaseRow[] };

/** Where the same case is shown with its map and its cards (a competition page). */
export const POLICY_CASE_ROUTE = "/command/planning/";

/** The label every score of the case carries, on its tile and above the table. */
export const POLICY_CASE_SCORE_LABEL: BilingualText = {
  en: "Case SE1 · scenario · stability not evaluated",
  th: "กรณี SE1 · สถานการณ์จำลอง · ยังไม่ได้ประเมินความเสถียร",
};

/** Why a row has its class, in the words of class rule v1 (`scoring.py`). */
export const POLICY_CASE_REASONS: Readonly<Record<string, BilingualText>> = {
  critical_route_access: {
    en: "Road criticality ≥75 and access gap ≥55",
    th: "ความสำคัญของถนน ≥75 และช่องว่างการเข้าถึง ≥55",
  },
  resilience: {
    en: "FPPS ≥35 and no earlier rule met",
    th: "FPPS ≥35 และไม่เข้าเงื่อนไขก่อนหน้า",
  },
  low_priority_score: {
    en: "FPPS under 35: lower relative priority, not a safety statement",
    th: "FPPS ต่ำกว่า 35: ลำดับความสำคัญเชิงเปรียบเทียบต่ำกว่า ไม่ใช่ข้อความยืนยันความปลอดภัย",
  },
};

/** A whole number of residents with thousands separators, the same in both languages. */
export function policyCaseCount(value: number): string {
  return Math.round(value).toLocaleString("en-US");
}
