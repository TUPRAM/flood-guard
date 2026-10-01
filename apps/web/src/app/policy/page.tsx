import type { Metadata } from "next";
import { PolicyPage } from "@/components/policy-page";

// The page switches language in the browser; its tab title and description carry both languages.
export const metadata: Metadata = {
  title: "Policy & public value · นโยบายและประโยชน์ต่อสังคม",
  description: "How FloodGuard turns flood evidence into preparedness priorities: FPPS, A–E action classes, equitable access and the fit with Thai policy, with a historical Mae Sai worked example. · FloodGuard แปลงหลักฐานน้ำท่วมเป็นลำดับความสำคัญในการเตรียมพร้อมอย่างไร: FPPS ระดับการดำเนินการ A–E การเข้าถึงอย่างเป็นธรรม และความสอดคล้องกับนโยบายไทย พร้อมตัวอย่างการคำนวณย้อนหลังของแม่สาย",
};

export default function PolicyRoute() {
  return <PolicyPage />;
}
