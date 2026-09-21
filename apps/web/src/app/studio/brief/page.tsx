import type { Metadata } from "next";
import { EvidenceLibrary } from "@/components/evidence-library";

export const metadata: Metadata = { title: "Decision brief | FloodGuard Thailand", description: "Concise research decisions, intervention comparisons and uncertainty for each FloodGuard study area." };
export default function DecisionBriefPage() { return <EvidenceLibrary view="brief" />; }
