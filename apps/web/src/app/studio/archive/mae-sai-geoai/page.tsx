import type { Metadata } from "next";

import { HistoricalStudy } from "@/components/historical-study";

export const metadata: Metadata = {
  title: "Historical Mae Sai GeoAI research — Studio",
  description: "Archived optical U-Net, teacher agreement, weak-label diagnosis and earlier Mae Sai GeoAI research with its original evidence and limitations.",
};

export default function HistoricalMaeSaiPage() {
  return <HistoricalStudy />;
}
