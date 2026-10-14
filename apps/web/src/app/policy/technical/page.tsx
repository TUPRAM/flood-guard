import type { Metadata } from "next";
import { PolicyPage } from "@/components/policy-page";

// The technical record behind the policy page: the scored case with all eight tambons, the signed scoring frame, the
// class rules and the earlier worked example. The page switches language in the browser.
export const metadata: Metadata = {
  title: "Policy: technical record · นโยบาย: บันทึกทางเทคนิค",
  description: "The technical record behind FloodGuard's policy page: case SE1 for the eight Mae Sai tambons, the signed scoring frame, the A–E class rules, access and equity definitions, and the earlier worked example. Planning support, not an official warning. · บันทึกทางเทคนิคของหน้านโยบาย FloodGuard: กรณี SE1 ของแปดตำบลในอำเภอแม่สาย กรอบการให้คะแนนที่ลงนาม กฎการจัดระดับ A–E และตัวอย่างการคำนวณก่อนหน้า ใช้สนับสนุนการวางแผน ไม่ใช่การเตือนภัยอย่างเป็นทางการ",
};

export default function PolicyTechnicalRoute() {
  return <PolicyPage />;
}
