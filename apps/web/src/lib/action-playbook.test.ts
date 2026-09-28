import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { ACTION_CLASSES } from "@floodguard/contracts";

import { ACTION_PLAYBOOK, PLAYBOOK_STAGES, stageForPhase } from "./action-playbook";

// Generated from floodguard.briefs by scripts/build_fpps_parity_fixture.py.
const fixture = JSON.parse(readFileSync(resolve(process.cwd(), "../../tests/fixtures/fpps_parity_cases.json"), "utf8")) as {
  recommended_actions: { en: Record<string, string>; th: Record<string, string> };
};

describe("action playbook", () => {
  it("uses the canonical recommended action from floodguard.briefs as each headline", () => {
    for (const key of ACTION_CLASSES) {
      expect(ACTION_PLAYBOOK[key].headline.en, key).toBe(fixture.recommended_actions.en[key]);
      expect(ACTION_PLAYBOOK[key].headline.th, key).toBe(fixture.recommended_actions.th[key]);
    }
  });

  it("gives every class responder and resident steps in both languages at every stage", () => {
    for (const key of ACTION_CLASSES) {
      for (const stage of PLAYBOOK_STAGES) {
        const actions = ACTION_PLAYBOOK[key].stages[stage];
        expect(actions.responders.length, `${key} ${stage}`).toBeGreaterThan(0);
        expect(actions.residents.length, `${key} ${stage}`).toBeGreaterThan(0);
        for (const line of [...actions.responders, ...actions.residents]) {
          expect(line.en.trim()).not.toBe("");
          expect(line.th).toMatch(/[฀-๿]/);
        }
      }
    }
  });

  it("tells residents to follow official warnings before the water and while it is high", () => {
    for (const key of ACTION_CLASSES) {
      for (const stage of ["before", "during"] as const) {
        expect(ACTION_PLAYBOOK[key].stages[stage].residents[0].en).toMatch(/DDPM \(hotline 1784\)/);
      }
    }
  });

  it("never claims to be a warning or real-time", () => {
    const all = JSON.stringify(ACTION_PLAYBOOK);
    expect(all).not.toMatch(/real-time|live feed|official warning system/i);
  });

  it("maps replay phases to stages", () => {
    expect(stageForPhase("dry")).toBe("before");
    expect(stageForPhase("onset")).toBe("during");
    expect(stageForPhase("peak")).toBe("during");
    expect(stageForPhase("receding")).toBe("after");
    expect(stageForPhase("gone")).toBe("after");
    expect(stageForPhase(null)).toBe("before");
  });
});
