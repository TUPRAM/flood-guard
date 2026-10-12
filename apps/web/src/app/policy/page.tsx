import type { Metadata } from "next";
import { PolicyBrief } from "@/components/policy-brief";

// The page switches language in the browser; its tab title and description carry both languages.
export const metadata: Metadata = {
  title: "Policy & public value · นโยบายและประโยชน์ต่อสังคม",
  description: "Flood maps show where the water goes; FloodGuard shows who could be cut off. What Thai disaster policy asks for, three practical proposals, one scenario example from Mae Sai, how the priority score works and who decides. Planning support, not an official warning. · แผนที่น้ำท่วมบอกว่าน้ำไปที่ใด FloodGuard แสดงว่าใครอาจถูกตัดขาด: สิ่งที่นโยบายภัยพิบัติของไทยให้ความสำคัญ ข้อเสนอสามข้อ ตัวอย่างสถานการณ์จำลองจากแม่สาย วิธีทำงานของคะแนน และผู้ตัดสินใจ ใช้สนับสนุนการวางแผน ไม่ใช่การเตือนภัยอย่างเป็นทางการ",
};

export default function PolicyRoute() {
  return <PolicyBrief />;
}
