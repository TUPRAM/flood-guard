export interface Mp4Box { type: string; start: number; size: number; header: number; body: number; end: number }
export interface ProgressiveMp4 { bytes: Buffer; seconds: number; samples: number; syncSamples: number; timescale: number }

export function readBoxes(buffer: Buffer, start?: number, end?: number): Mp4Box[];
export function box(type: string, ...payloads: Buffer[]): Buffer;
export function fullBox(type: string, version: number, flags: number, ...payloads: Buffer[]): Buffer;
export function progressiveMp4(input: Buffer): ProgressiveMp4;
