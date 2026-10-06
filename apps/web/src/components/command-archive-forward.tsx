"use client";

import { useEffect } from "react";

import { PLANNING_OVERVIEW_ROUTE, PLANNING_WORKSPACE_ROUTE, RESEARCH_WORKSPACE_ROUTE } from "@/lib/case-selection";

import styles from "./command-archive-forward.module.css";

/** Where an old address sends a reader: the new address, with the query and fragment the old link carried. */
export function forwardTarget(to: string, search: string, hash: string): string {
  return `${to}${search}${hash}`;
}

/** Where /command/archive/ sends a reader: the older map workspace in Studio's archive. */
export function commandArchiveForwardTarget(search: string, hash: string): string {
  return forwardTarget(RESEARCH_WORKSPACE_ROUTE, search, hash);
}

/**
 * What an address that has moved serves (decision log R19 and R24). The page has no content of its own: it sends the
 * browser on and keeps the query of the old link, so that links, bookmarks and saved offline copies keep working.
 * The sentence and its link are for a reader whose browser has not run the script. It shows no score and no class.
 */
export function AddressForward({ to, en, th }: { to: string; /** What moved, as the subject of the sentence. */ en: string; th: string }) {
  useEffect(() => {
    window.location.replace(forwardTarget(to, window.location.search, window.location.hash));
  }, [to]);

  return (
    <main id="main-content" tabIndex={-1} className={styles.forward} data-command-forward={to}>
      <p lang="en">{`This page has moved. ${en} is now at `}<a href={to}>{to}</a>.</p>
      <p lang="th">{`หน้านี้ย้ายแล้ว ${th}อยู่ที่ `}<a href={to}>{to}</a></p>
    </main>
  );
}

/** /command/archive/: the older map workspace, now historical research in Studio's archive. */
export function CommandArchiveForward() {
  return <AddressForward to={RESEARCH_WORKSPACE_ROUTE} en="The older Planning map workspace, kept as historical research," th="พื้นที่ทำงานแผนที่เดิมซึ่งเก็บไว้เป็นงานวิจัยย้อนหลัง" />;
}

/** /command/ver2/: the planning overview. */
export function PlanningOverviewForward() {
  return <AddressForward to={PLANNING_OVERVIEW_ROUTE} en="The planning overview" th="ภาพรวมเพื่อการวางแผน" />;
}

/** /command/exercise/: the Command exercise replay, now the default Planning page. */
export function CommandExerciseForward() {
  return <AddressForward to={PLANNING_WORKSPACE_ROUTE} en="The Command exercise replay" th="หน้าฝึกซ้อมสั่งการ" />;
}
