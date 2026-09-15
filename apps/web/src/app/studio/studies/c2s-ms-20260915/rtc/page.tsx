import type { Metadata } from "next";
import { C2sStudyWorkspace } from "@/components/c2s-study-workspace";
export const metadata: Metadata = { title: "C2S-MS · Matched RTC comparison" };
export default function C2sRtcPage() { return <C2sStudyWorkspace section="rtc" />; }
