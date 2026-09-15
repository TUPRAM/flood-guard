import type { Metadata } from "next";
import { C2sStudyWorkspace } from "@/components/c2s-study-workspace";
export const metadata: Metadata = { title: "Mae Sai · Application of C2S models", description: "Report-only application of C2S-trained models to Mae Sai radar imagery. No qualified Thai reference is available; local accuracy has not been measured." };
export default function C2sMaeSaiPage() { return <C2sStudyWorkspace section="mae-sai" />; }
