import type { Metadata } from "next";

import { StudioWorkspace } from "@/components/studio-workspace";

export const metadata: Metadata = { title: "Research studio" };

export default function StudioPage() {
  return <div id="main-content"><StudioWorkspace /></div>;
}
