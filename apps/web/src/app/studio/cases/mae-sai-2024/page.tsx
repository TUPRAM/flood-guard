import type { Metadata } from "next";

import { MaeSaiFloodTimeline } from "@/components/mae-sai-flood-timeline";

export const metadata: Metadata = {
  title: "Mae Sai flood, September 2024 — day by day — Studio",
  description: "Replay the September 2024 Mae Sai flood from 9 to 19 September: dated Sentinel-2 and Sentinel-1 imagery layered with a low-confidence terrain-model water reconstruction, hour-by-hour modelled road, facility and residents-in-water figures, a walking-access-to-shelter scenario with its equity gap, the shelters reported in 2024 and a ranked shelter plan. Historical reconstruction and planning scenarios, not real-time and not an official warning.",
};

export default function MaeSaiFloodTimelinePage() {
  return <MaeSaiFloodTimeline />;
}
