import type { Metadata } from "next";

import { CommandWorkspace } from "@/components/command-workspace";

export const metadata: Metadata = {
  title: "Planning workspace",
  description: "Mae Sai area planning, evidence review, and verification workspace.",
};

export default function CommandPage() {
  return <div id="main-content"><CommandWorkspace /></div>;
}
