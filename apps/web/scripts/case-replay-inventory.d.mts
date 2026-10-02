export interface CaseReplayAsset { url: string; sha256: string; bytes: number }
export interface CaseReplayExportPack { budget_bytes: number; bytes: number; assets: CaseReplayAsset[] }
export interface CaseReplayInventory {
  policy: string;
  route: string;
  manifest: string;
  budget_bytes: number;
  bytes: number;
  assets: CaseReplayAsset[];
  exports: CaseReplayExportPack;
}

export const CASE_REPLAY_ROUTE: string;
export const caseReplayInventory: string;
export const CASE_REPLAY_POLICY: string;
export const CASE_REPLAY_BUDGET_BYTES: number;
export const CASE_REPLAY_EXPORT_BUDGET_BYTES: number;
export const CASE_REPLAY_EXPORT_KEY: string;
export function timelineManifestUrl(root?: string): string;
export function manifestDirectory(manifestUrl: string): string;
export function timelineManifestAssets(manifest: unknown): { href: string; sha256: string; bytes: number }[];
export function timelineExportAssets(manifest: unknown): { href: string; sha256: string; bytes: number }[];
export function readCaseReplayAssets(root: string, manifestUrl?: string): { manifest: unknown; assets: CaseReplayAsset[] };
export function readCaseReplayExports(root: string, manifestUrl?: string): CaseReplayAsset[];
export function caseReplayBytes(assets: readonly { bytes: number }[], budget?: number): number;
export function caseReplayExportBytes(assets: readonly { bytes: number }[], budget?: number): number;
export function collectCaseReplay(out: string): CaseReplayAsset[];
export function readCaseReplay(out: string): CaseReplayInventory;
