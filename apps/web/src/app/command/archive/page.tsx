import type { Metadata } from "next";

import { CommandArchiveForward } from "@/components/command-archive-forward";

// The map workspace that was served here is the default Planning page at /command/ since the owner's request of
// 5 Oct 2026 (decision log R19). This address only forwards to it. The page carries both languages in its one
// sentence, as its tab title does.
export const metadata: Metadata = {
  title: "Moved to Planning · ย้ายไปที่หน้าการวางแผนแล้ว | FloodGuard",
  description: "This address forwards to the Planning map workspace at /command/. · ที่อยู่นี้ส่งต่อไปยังพื้นที่ทำงานแผนที่สำหรับการวางแผนที่ /command/",
};

export default function CommandArchivePage() {
  return <CommandArchiveForward />;
}
