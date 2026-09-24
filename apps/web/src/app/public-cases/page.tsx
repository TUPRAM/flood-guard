import type { Metadata } from "next";
import { EvidenceLibrary } from "@/components/evidence-library";

export const metadata: Metadata = { title: "Study cases | FloodGuard", description: "Plain-language, non-operational explanations of shared FloodGuard research cases." };
export default function PublicCasesPage() { return <EvidenceLibrary view="public" role="public" />; }
