import type { Metadata } from "next";
import { C2sStudyWorkspace } from "@/components/c2s-study-workspace";
export const metadata: Metadata = { title: "C2S-MS · Visual error explorer" };
export default function C2sExplorerPage() { return <C2sStudyWorkspace section="explorer" />; }
