import type { Metadata } from "next";

import { MaeSaiFloodTimeline } from "@/components/mae-sai-flood-timeline";
import { ARCHIVE_1_MANIFEST_URL } from "@/lib/flood-timeline";

export const metadata: Metadata = {
  title: "Archive 1: Mae Sai flood replay, revision r4 — Studio",
  description: "The Mae Sai September 2024 flood replay as it stood before 12 October 2026 (revision r4), kept unchanged for comparison with the current replay, whose peak is fitted to the satellite image of 15 September 2024. Historical reconstruction and planning scenarios, not real-time and not an official warning.",
  robots: { index: false },
};

export default function MaeSaiFloodTimelineArchive1Page() {
  return <MaeSaiFloodTimeline manifestUrl={ARCHIVE_1_MANIFEST_URL} archive />;
}
