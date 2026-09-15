import type { Metadata } from "next";
import { C2sStudyWorkspace } from "@/components/c2s-study-workspace";
export const metadata: Metadata = { title: "C2S-MS · Benchmark results" };
export default function C2sResultsPage() { return <C2sStudyWorkspace section="results" />; }
