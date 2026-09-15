import type { Metadata } from "next";

import { StudioLibrary } from "@/components/studio-library";

export const metadata: Metadata = {
  title: "Studio — Studies & evidence",
  description: "Explore separate FloodGuard research studies, benchmark evaluations, planning evidence and historical reports.",
};

export default function StudioPage() {
  return <StudioLibrary />;
}
