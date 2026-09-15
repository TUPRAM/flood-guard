import type { Metadata } from "next";
import { C2sStudyWorkspace } from "@/components/c2s-study-workspace";
export const metadata: Metadata = { title: "C2S-MS · Data & event split" };
export default function C2sDataPage() { return <C2sStudyWorkspace section="data" />; }
