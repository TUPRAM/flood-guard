"use client";

import { useEffect, useState } from "react";

import {
  loadProposalEvidence,
  type ProposalEvidenceResult,
} from "./proposal-evidence";

export type ProposalEvidenceViewState =
  | { state: "loading" }
  | ProposalEvidenceResult;

export function useProposalEvidence(): ProposalEvidenceViewState {
  const [result, setResult] = useState<ProposalEvidenceViewState>({ state: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    void loadProposalEvidence(fetch, controller.signal).then((next) => {
      if (active) setResult(next);
    });
    return () => {
      active = false;
      controller.abort();
    };
  }, []);

  return result;
}
