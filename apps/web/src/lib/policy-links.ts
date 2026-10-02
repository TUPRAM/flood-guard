import { resolveDeploymentProfile } from "./deployment-profile";

/** The bilingual policy brief (`src/app/policy`). */
export const POLICY_ROUTE = "/policy/";

/** The current Mae Sai replay (revision in `POLICY_EVIDENCE.currentReplay`). A unit test keeps it equal to the replay's own route constants. */
export const MAE_SAI_REPLAY_ROUTE = "/studio/cases/mae-sai-2024/";

/**
 * Whether this build ships the competition-only pages (`/policy/` and everything under `/studio/`).
 *
 * For the public-production profile `scripts/build-profile.mjs` moves those routes aside before `next build`,
 * `write-offline-assets.mjs` leaves them out of the offline cache, and `profile-artifact-smoke.mjs` fails the build
 * if a link to them remains, so a link to either page must not render there. `NEXT_PUBLIC_*` is inlined at build
 * time, so the server and client renders agree.
 */
export function competitionPagesAvailable(profile: string | undefined = process.env.NEXT_PUBLIC_FLOODGUARD_APP_PROFILE): boolean {
  return resolveDeploymentProfile(profile) === "competition";
}
