import type { Metadata } from "next";
import { C2sStudyWorkspace } from "@/components/c2s-study-workspace";
export const metadata: Metadata = { title: "C2S-MS · Files & reproducibility" };
export default function C2sFilesPage() { return <C2sStudyWorkspace section="files" />; }
