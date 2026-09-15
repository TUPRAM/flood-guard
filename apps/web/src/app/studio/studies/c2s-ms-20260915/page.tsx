import type { Metadata } from "next";
import { C2sStudyWorkspace } from "@/components/c2s-study-workspace";

export const metadata: Metadata = { title: "C2S-MS public benchmark", description: "Event-separated Random Forest, XGBoost and SAR U-Net evaluation against C2S-MS human water labels. Research report only." };
export default function C2sOverviewPage() { return <C2sStudyWorkspace section="overview" />; }
