export interface CaseReplayAsset { url: string; sha256: string; bytes: number }
export interface CaseReplayInventory {
  policy: string;
  route: string;
  manifest: string;
  bytes: number;
  assets: CaseReplayAsset[];
}

export const CASE_REPLAY_ROUTE: string;
export const caseReplayInventory: string;
export const CASE_REPLAY_POLICY: string;
export function timelineManifestUrl(root?: string): string;
export function manifestDirectory(manifestUrl: string): string;
export function timelineManifestAssets(manifest: unknown): { href: string; sha256: string; bytes: number }[];
export function readCaseReplayAssets(root: string, manifestUrl?: string): { manifest: unknown; assets: CaseReplayAsset[] };
export function collectCaseReplay(out: string): CaseReplayAsset[];
export function readCaseReplay(out: string): CaseReplayInventory;
