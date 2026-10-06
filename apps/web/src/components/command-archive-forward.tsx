"use client";

import { useEffect } from "react";

import { PLANNING_WORKSPACE_ROUTE } from "@/lib/case-selection";

import styles from "./command-archive-forward.module.css";

/** Where the old address sends a reader: the map workspace, with the query and fragment the old link carried. */
export function commandArchiveForwardTarget(search: string, hash: string): string {
  return `${PLANNING_WORKSPACE_ROUTE}${search}${hash}`;
}

/**
 * What /command/archive/ serves since the owner's request of 5 Oct 2026 (decision log R19). The map workspace it
 * showed is now the default Planning page at /command/. This page has no content of its own: it sends the browser
 * on and keeps the query of the old link, so that links, bookmarks and saved offline copies keep working. The
 * sentence and its link are for a reader whose browser has not run the script. It shows no score and no class.
 */
export function CommandArchiveForward() {
  useEffect(() => {
    window.location.replace(commandArchiveForwardTarget(window.location.search, window.location.hash));
  }, []);

  return (
    <main id="main-content" tabIndex={-1} className={styles.forward} data-command-forward={PLANNING_WORKSPACE_ROUTE}>
      <p lang="en">This page has moved. The Planning map workspace is now at <a href={PLANNING_WORKSPACE_ROUTE}>{PLANNING_WORKSPACE_ROUTE}</a>.</p>
      <p lang="th">หน้านี้ย้ายแล้ว พื้นที่ทำงานแผนที่สำหรับการวางแผนอยู่ที่ <a href={PLANNING_WORKSPACE_ROUTE}>{PLANNING_WORKSPACE_ROUTE}</a></p>
    </main>
  );
}
