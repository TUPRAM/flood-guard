import type { Metadata } from "next";

import { CommandExerciseForward } from "@/components/command-archive-forward";

// The exercise replay was built at this address. It is the default Planning page at /command/ since 7 Oct 2026
// (decision log R24), and this address only forwards to it.
export const metadata: Metadata = {
  title: "Moved to Planning · ย้ายไปที่หน้าการวางแผนแล้ว | FloodGuard",
  description: "This address forwards to the Command exercise replay at /command/. · ที่อยู่นี้ส่งต่อไปยังหน้าฝึกซ้อมสั่งการที่ /command/",
};

export default function CommandExerciseForwardPage() {
  return <CommandExerciseForward />;
}
