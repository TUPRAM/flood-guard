"use client";

import { loadStudySummary } from "@/lib/study-report";
import type { StudySummary } from "@/lib/study-report-types";
import { StudyData, StudyModels, StudyOverview, StudyResults } from "./c2s-study-benchmark";
import { StudyExplorer, StudyFiles, StudyMaeSai, StudyRtc } from "./c2s-study-inference";
import { Loading, StudyFrame, Unavailable, useStudyQuery, useStudyResource, type StudySection } from "./c2s-study-shared";

export function StudySectionContent({ section, report }: { section: StudySection; report: StudySummary }) {
  switch (section) {
    case "overview": return <StudyOverview report={report} />;
    case "data": return <StudyData report={report} />;
    case "models": return <StudyModels report={report} />;
    case "results": return <StudyResults report={report} />;
    case "rtc": return <StudyRtc report={report} />;
    case "explorer": return <StudyExplorer report={report} />;
    case "files": return <StudyFiles report={report} />;
    case "mae-sai": return <StudyMaeSai report={report} />;
  }
}

export function C2sStudyWorkspace({ section = "overview" }: { section?: StudySection }) {
  const study = useStudyResource("c2s-ms-20260915:r1", loadStudySummary);
  const { values } = useStudyQuery();
  const revision = values.get("revision") ?? "r1";
  return <StudyFrame section={section}>{revision !== "r1" ? <Unavailable title="Study revision unavailable" reason={`Revision “${revision}” is not available at this address. This route is bound to revision r1.`} /> : study.error ? <Unavailable reason={study.error} /> : study.data ? <StudySectionContent section={section} report={study.data} /> : <Loading />}</StudyFrame>;
}
