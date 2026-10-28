import type { Metadata } from "next";
import { JournalPage } from "@/components/journal-page";

// The reference list shared with the audience by QR code. The page switches language in the browser.
export const metadata: Metadata = {
  title: "References · เอกสารอ้างอิง",
  description: "The papers, data and software behind FloodGuard, grouped by the step of the system each one stands behind: radar, terrain, models, access, people, the priority score and Thai law. Planning support, not an official warning. · งานวิจัย ข้อมูล และซอฟต์แวร์เบื้องหลัง FloodGuard จัดกลุ่มตามขั้นตอนของระบบ: เรดาร์ ภูมิประเทศ แบบจำลอง การเข้าถึง ประชาชน คะแนนลำดับความสำคัญ และกฎหมายไทย ใช้สนับสนุนการวางแผน ไม่ใช่การเตือนภัยอย่างเป็นทางการ",
};

export default function JournalRoute() {
  return <JournalPage />;
}
