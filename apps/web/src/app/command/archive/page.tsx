import type { Metadata } from "next";

import { CommandArchiveForward } from "@/components/command-archive-forward";

// The older map workspace was served here until 5 Oct 2026 and at /command/ until 7 Oct 2026. It is kept as historical
// research in Studio's archive (decision log R24), and this address only forwards to it.
export const metadata: Metadata = {
  title: "Moved to Studio's archive · ย้ายไปที่คลังของ Studio แล้ว | FloodGuard",
  description: "This address forwards to the historical Planning map workspace in Studio's archive. · ที่อยู่นี้ส่งต่อไปยังพื้นที่ทำงานแผนที่เดิมในคลังของ Studio",
};

export default function CommandArchivePage() {
  return <CommandArchiveForward />;
}
