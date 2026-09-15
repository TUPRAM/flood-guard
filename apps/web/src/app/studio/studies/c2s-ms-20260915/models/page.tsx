import type { Metadata } from "next";
import { C2sStudyWorkspace } from "@/components/c2s-study-workspace";
export const metadata: Metadata = { title: "C2S-MS · Models & training" };
export default function C2sModelsPage() { return <C2sStudyWorkspace section="models" />; }
