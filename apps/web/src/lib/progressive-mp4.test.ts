/**
 * The rewrite of a browser's fragmented MP4 recording as a progressive MP4 (`scripts/progressive-mp4.mjs`), used for the
 * venue-fallback video of the replay (roadmap P4-1). On a small synthetic recording built here: the sample bytes are
 * copied unchanged and in order, every sample's size, duration and key-frame flag reach the sample tables, the last
 * frame of a fragment lasts until the next fragment starts (the recorder only guesses it), the duration is written into
 * the headers, the moov comes before the media data and nothing fragmented is left. Anything that is not a one-track
 * fragmented recording is refused.
 */

import { describe, expect, it } from "vitest";

import { progressiveMp4, readBoxes } from "../../scripts/progressive-mp4.mjs";

const u32 = (...values: number[]) => {
  const out = Buffer.alloc(4 * values.length);
  values.forEach((value, index) => out.writeUInt32BE(value >>> 0, index * 4));
  return out;
};
const u64 = (value: number) => {
  const out = Buffer.alloc(8);
  out.writeBigUInt64BE(BigInt(value));
  return out;
};
const box = (type: string, ...payloads: Buffer[]) => {
  const body = Buffer.concat(payloads);
  return Buffer.concat([u32(8 + body.length), Buffer.from(type, "latin1"), body]);
};
const full = (type: string, version: number, flags: number, ...payloads: Buffer[]) => box(type, u32((version << 24) | flags), ...payloads);

const MEDIA_TIMESCALE = 90_000;
const NON_SYNC = 0x10000;
type Sample = { duration: number; data: string; sync: boolean };

function moov(tracks = 1): Buffer {
  const mvhd = full("mvhd", 0, 0, u32(0, 0, 1000, 0, 0x10000), Buffer.alloc(2 + 10 + 36 + 24), u32(2));
  const trak = (id: number) => box("trak",
    full("tkhd", 0, 3, u32(0, 0, id, 0, 3718), Buffer.alloc(8 + 8 + 36), u32(1280 << 16, 720 << 16)),
    box("mdia",
      full("mdhd", 0, 0, u32(0, 0, MEDIA_TIMESCALE, 3718), Buffer.alloc(4)),
      full("hdlr", 0, 0, u32(0), Buffer.from("vide", "latin1"), Buffer.alloc(12), Buffer.from([0])),
      box("minf",
        full("vmhd", 0, 1, Buffer.alloc(8)),
        box("dinf", full("dref", 0, 0, u32(1), full("url ", 0, 1))),
        box("stbl",
          full("stsd", 0, 0, u32(1), box("avc1", Buffer.from("sample-entry", "latin1"))),
          full("stts", 0, 0, u32(0)), full("stsc", 0, 0, u32(0)), full("stsz", 0, 0, u32(0, 0)), full("stco", 0, 0, u32(0))))));
  const traks = Array.from({ length: tracks }, (_, index) => trak(index + 1));
  return box("moov", mvhd, ...traks, box("mvex", ...Array.from({ length: tracks }, (_, index) => full("trex", 0, 0, u32(index + 1, 1, 0, 0, 0)))));
}

/** One fragment as MediaRecorder writes it: default sample flags "non-sync", the first sample's own flags, durations and sizes. */
function fragment(sequence: number, baseDecodeTime: number, samples: Sample[]): Buffer {
  const build = (dataOffset: number) => box("moof",
    full("mfhd", 0, 0, u32(sequence)),
    box("traf",
      full("tfhd", 0, 0x20020, u32(1, NON_SYNC)),
      full("tfdt", 1, 0, u64(baseDecodeTime)),
      full("trun", 1, 0x305, u32(samples.length, dataOffset, samples[0].sync ? 0x02000000 : NON_SYNC),
        ...samples.map((sample) => u32(sample.duration, sample.data.length)))));
  const size = build(0).length;
  return Buffer.concat([build(size + 8), box("mdat", Buffer.from(samples.map((sample) => sample.data).join(""), "latin1"))]);
}

function recording(nextBase = 9000): Buffer {
  return Buffer.concat([
    box("ftyp", Buffer.from("iso5", "latin1"), u32(512), Buffer.from("iso5iso6mp41", "latin1")),
    moov(),
    // The recorder guesses the last frame of each fragment at one frame period (999); the next fragment's decode time is the truth.
    fragment(1, 0, [{ duration: 3000, data: "AAAAA", sync: true }, { duration: 3000, data: "BBB", sync: false }, { duration: 999, data: "CCCC", sync: false }]),
    fragment(2, nextBase, [{ duration: 3000, data: "DD", sync: true }, { duration: 3000, data: "EEEEEE", sync: false }]),
  ]);
}

/** The sample tables of the rewritten file, read back. */
function tables(bytes: Buffer) {
  const top = readBoxes(bytes);
  const moovBox = top.find((item) => item.type === "moov")!;
  const find = (parent: { body: number; end: number }, type: string) => readBoxes(bytes, parent.body, parent.end).find((item) => item.type === type)!;
  const trak = find(moovBox, "trak");
  const mdia = find(trak, "mdia");
  const stbl = find(find(mdia, "minf"), "stbl");
  const entries = (type: string, width: number, skip = 0) => {
    const found = find(stbl, type);
    if (!found) return null;
    const count = bytes.readUInt32BE(found.body + 4 + skip);
    return Array.from({ length: count }, (_, row) => Array.from({ length: width }, (_, column) => bytes.readUInt32BE(found.body + 8 + skip + (row * width + column) * 4)));
  };
  return {
    top: top.map((item) => item.type),
    mvhdDuration: bytes.readUInt32BE(find(moovBox, "mvhd").body + 16),
    tkhdDuration: bytes.readUInt32BE(find(trak, "tkhd").body + 20),
    mdhdDuration: bytes.readUInt32BE(find(mdia, "mdhd").body + 16),
    stts: entries("stts", 2),
    stss: entries("stss", 1)?.flat() ?? null,
    stsc: entries("stsc", 3),
    stsz: entries("stsz", 1, 4)?.flat(),
    stco: entries("stco", 1)?.flat(),
    moovChildren: readBoxes(bytes, moovBox.body, moovBox.end).map((item) => item.type),
    stsd: bytes.subarray(find(stbl, "stsd").start, find(stbl, "stsd").end).toString("latin1"),
  };
}

describe("progressive MP4 rewrite of a fragmented recording", () => {
  it("copies every sample unchanged and in order into one media box after the moov", () => {
    const result = progressiveMp4(recording());
    const read = tables(result.bytes);
    expect(read.top).toEqual(["ftyp", "moov", "mdat"]);
    expect(read.moovChildren).toEqual(["mvhd", "trak"]);
    expect(read.stsz).toEqual([5, 3, 4, 2, 6]);
    expect(read.stsc).toEqual([[1, 3, 1], [2, 2, 1]]);
    expect(read.stco!.map((offset, index) => result.bytes.subarray(offset, offset + [12, 8][index]).toString("latin1"))).toEqual(["AAAAABBBCCCC", "DDEEEEEE"]);
    expect(read.stsd).toContain("sample-entry");
    expect(result.samples).toBe(5);
  });

  it("keeps the key frames and lets a fragment's last frame last until the next fragment starts", () => {
    const result = progressiveMp4(recording());
    const read = tables(result.bytes);
    expect(read.stss).toEqual([1, 4]);
    expect(result.syncSamples).toBe(2);
    // 3000 + 3000 + (9000 - 6000) + 3000 + 3000: the guessed 999 becomes 3000.
    expect(read.stts).toEqual([[5, 3000]]);
  });

  it.each([
    [8500, [[2, 3000], [1, 2500], [2, 3000]]],
    [6500, [[2, 3000], [1, 500], [2, 3000]]],
  ])("corrects the guessed duration when the next fragment starts at %i", (nextBase, stts) => {
    expect(tables(progressiveMp4(recording(nextBase)).bytes).stts).toEqual(stts);
  });

  it("writes the true duration into the movie, track and media headers", () => {
    const result = progressiveMp4(recording());
    const read = tables(result.bytes);
    expect(read.mdhdDuration).toBe(15_000);
    expect(read.mvhdDuration).toBe(167);
    expect(read.tkhdDuration).toBe(167);
    expect(result.seconds).toBeCloseTo(15_000 / MEDIA_TIMESCALE, 10);
    expect(result.timescale).toBe(MEDIA_TIMESCALE);
  });

  it("refuses a file without fragments, with two tracks, or with fragments that overlap a whole frame", () => {
    const ftyp = box("ftyp", Buffer.from("isom", "latin1"), u32(0));
    expect(() => progressiveMp4(Buffer.concat([ftyp, moov()]))).toThrow(/no fragments/);
    expect(() => progressiveMp4(Buffer.concat([ftyp, moov(2)]))).toThrow(/one track/);
    expect(() => progressiveMp4(recording(5000))).toThrow(/overlap/);
    expect(() => progressiveMp4(Buffer.concat([moov(), ftyp]))).toThrow(/start with ftyp/);
  });
});
