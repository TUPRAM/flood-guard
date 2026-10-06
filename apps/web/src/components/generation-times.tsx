/** Keep source analysis creation separate from the package's later release time. */
export function GenerationTimes({ sourceAnalysisGeneratedAt, releaseGeneratedAt, th, className }: {
  sourceAnalysisGeneratedAt: string | null;
  releaseGeneratedAt: string;
  th: boolean;
  className?: string;
}) {
  return <p className={className} data-source-analysis-generated-at={sourceAnalysisGeneratedAt ?? "unavailable"} data-package-release-generated-at={releaseGeneratedAt}>
    {th ? "สร้างผลวิเคราะห์ต้นทางเมื่อ" : "Source analysis generated"}: {sourceAnalysisGeneratedAt
      ? <time dateTime={sourceAnalysisGeneratedAt}>{sourceAnalysisGeneratedAt}</time>
      : <span>{th ? "ยังไม่มีผลวิเคราะห์ต้นทาง" : "Unavailable (no source analysis)"}</span>}
    {" · "}{th ? "สร้างแพ็กเกจเผยแพร่เมื่อ" : "Package release generated"}: <time dateTime={releaseGeneratedAt}>{releaseGeneratedAt}</time>
  </p>;
}
