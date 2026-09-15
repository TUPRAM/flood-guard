# Repository integration notes — limited inspection

Inspected 15 September 2026 through the GitHub connector on the repository's default branch, which resolved as `master`. This is NOT a full repository audit and does not establish the state of the owner's local checkout. Earlier screenshots contain a newer landing design than the root file retrieved here. Codex must inspect local changes and preserve them.

## Confirmed files

`apps/web/package.json` identified @floodguard/web. It listed Next 16.2.6, React/ReactDOM 19.2.4, TypeScript 5.7.3, Playwright 1.61.1, Vitest 3.2.4, Leaflet, local fontsource packages, and scripts for dev/build, competition/public builds, lint, typecheck, test, offline, CSP, live API and visual QA. GSAP and React Three Fiber were not listed in that retrieved file. Do not assume the local dependencies are identical or upgrade them to these versions if they differ.

`apps/web/src/app/page.tsx` exported SurfaceChooser and a RootEntry function. It resolved `FLOODGUARD_APP_PROFILE ?? NEXT_PUBLIC_FLOODGUARD_APP_PROFILE`; public-production returned PublicExperience, otherwise SurfaceChooser. Preserve the profile behavior and any callers/tests of named exports. Integrate the new landing inside the appropriate existing branch rather than blindly replacing the root.

`apps/web/next.config.ts` declared `output: "export"`, `trailingSlash: true`, and `images: { unoptimized: true }`. The new page must work on static hosting without the default runtime image optimizer. Preserve other config and CSP behavior.

`apps/web/scripts/write-offline-assets.mjs` walked `_next/static`, assembled explicit profile core assets, emitted deployment-profile metadata, generated a version hash from content and service-worker policy, and pruned staff/evidence artifacts for public-production. New files under public are not automatically included in every explicit list or hash. Read the actual local script and service worker; integrate the landing artwork deliberately without precaching all references or breaking the public profile.

## Required local audit targets

Read applicable AGENTS instructions, git status/diff, package scripts and lockfile, app/page and layout, existing landing directories, profile resolver/build-profile scripts, offline asset builder and SW, global styles/fonts, current localization, security headers/CSP and tests. Search actual imports before removing old R3F/generated-town components. There may be a newer local scene implementation that is absent from default-branch GitHub.

Do not modify API/domain methods, evidence-gate statuses, permissions, actual flood findings, or historical metrics to make the marketing animation work. The local story is synthetic and separate.

## Source file identifiers for reproducibility

- package.json blob: dab0a7674bd799716a75e5590027c8462d62b95b
- src/app/page.tsx blob: 165bff70f6c2c59e4250e19d4ddd58205e455947
- next.config.ts blob: 126c90541b6680bf2a34909382ab0283fa2095ac
- scripts/write-offline-assets.mjs blob: 56f05797faef623179f89013028079c73796889a

These are file hashes from the retrieved default branch, not a known global repository commit. No private source file was downloaded into this handoff; the owner already has the repository.
