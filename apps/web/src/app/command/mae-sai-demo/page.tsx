import type { Metadata } from "next";

import { MaeSaiPlanningDemo } from "@/components/mae-sai-planning-demo";

export const metadata: Metadata = {
  title: "Mae Sai historical planning case",
  description: "Explore a traceable Mae Sai historical case, compare access assumptions, and preserve a local planning decision record.",
};

export default function MaeSaiDemoPage() {
  return <MaeSaiPlanningDemo />;
}
