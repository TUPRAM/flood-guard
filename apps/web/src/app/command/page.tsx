import type { Metadata } from "next";

import { CommandWorkspace } from "@/components/command-workspace";

export const metadata: Metadata = { title: "Planning command center" };

export default function CommandPage() {
  return <div id="main-content"><CommandWorkspace /></div>;
}
