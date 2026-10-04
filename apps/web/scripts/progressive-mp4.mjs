/**
 * Rewrite a fragmented MP4 as a progressive ("fast start") MP4, without re-encoding.
 *
 * A browser's MediaRecorder writes MP4 as fragments: an `ftyp`, a `moov` whose sample tables are empty (plus an `mvex`),
 * then `moof` + `mdat` pairs. Chromium also leaves the duration fields of that `moov` wrong or zero, so players show a
 * few seconds and cannot seek. This module reads every fragment's samples (size, duration, sync flag, composition
 * offset) and writes one `moov` with full sample tables (stts, ctts, stss, stsc, stsz, stco) and the true duration,
 * followed by one `mdat` holding the same sample bytes in the same order. One track only (the replay export is video
 * only); anything else is refused rather than guessed.
 */

/** Sample flag "sample_is_non_sync_sample": the frame is not a key frame. */
const NON_SYNC = 0x10000;

/** Boxes directly inside `buffer[start, end)`: type, start, total size and header length. */
export function readBoxes(buffer, start = 0, end = buffer.length) {
  const boxes = [];
  let at = start;
  while (at < end) {
    if (at + 8 > end) throw new Error(`Truncated box header at byte ${at}`);
    let size = buffer.readUInt32BE(at);
    const type = buffer.toString("latin1", at + 4, at + 8);
    let header = 8;
    if (size === 1) {
      size = Number(buffer.readBigUInt64BE(at + 8));
      header = 16;
    } else if (size === 0) size = end - at;
    if (size < header || at + size > end) throw new Error(`Box ${type} at byte ${at} overruns its parent`);
    boxes.push({ type, start: at, size, header, body: at + header, end: at + size });
    at += size;
  }
  return boxes;
}

/** The single child box of `type` inside `parent` (or null). */
function child(buffer, parent, type) {
  const found = readBoxes(buffer, parent.body, parent.end).filter((box) => box.type === type);
  if (found.length > 1) throw new Error(`More than one ${type} box`);
  return found[0] ?? null;
}

function need(found, type) {
  if (!found) throw new Error(`The MP4 has no ${type} box`);
  return found;
}

/** Build a box from its type and payload buffers. */
export function box(type, ...payloads) {
  const body = Buffer.concat(payloads);
  const header = Buffer.alloc(8);
  header.writeUInt32BE(8 + body.length, 0);
  header.write(type, 4, "latin1");
  return Buffer.concat([header, body]);
}

/** A full box: version and 24-bit flags, then the payload. */
export function fullBox(type, version, flags, ...payloads) {
  const head = Buffer.alloc(4);
  head.writeUInt32BE(((version & 0xff) << 24) | (flags & 0xffffff), 0);
  return box(type, head, ...payloads);
}

const u32 = (...values) => {
  const out = Buffer.alloc(4 * values.length);
  values.forEach((value, index) => out.writeUInt32BE(value >>> 0, index * 4));
  return out;
};

/** Copy a header box (mvhd, tkhd, mdhd) with its duration field set; `field` gives the v0 and v1 byte offsets in the body. */
function withDuration(buffer, original, duration, field) {
  const copy = Buffer.from(buffer.subarray(original.start, original.end));
  const version = copy[original.header];
  const at = original.header + (version === 1 ? field.v1 : field.v0);
  if (version === 1) copy.writeBigUInt64BE(BigInt(duration), at);
  else {
    if (duration > 0xffffffff) throw new Error("Duration too long for a version 0 header");
    copy.writeUInt32BE(duration, at);
  }
  return copy;
}

function timescaleOf(buffer, original, field) {
  const version = buffer[original.body];
  return buffer.readUInt32BE(original.body + (version === 1 ? field.v1 : field.v0));
}

/** Run-length entries of consecutive equal values: [[count, value], …]. */
function runs(values) {
  const out = [];
  for (const value of values) {
    const last = out.at(-1);
    if (last && last[1] === value) last[0] += 1;
    else out.push([1, value]);
  }
  return out;
}

/** Every sample of every fragment of track `trackId`, in decode order, with the byte range it occupies in `buffer`. */
function fragmentSamples(buffer, top, trackId, trex) {
  const samples = [];
  const chunks = [];
  let decodeTime = null;
  for (const moof of top.filter((item) => item.type === "moof")) {
    const trafs = readBoxes(buffer, moof.body, moof.end).filter((item) => item.type === "traf");
    if (trafs.length !== 1) throw new Error("Each fragment must hold exactly one track fragment");
    const traf = trafs[0];
    const tfhd = need(child(buffer, traf, "tfhd"), "tfhd");
    const flags = buffer.readUIntBE(tfhd.body + 1, 3);
    let at = tfhd.body + 4;
    if (buffer.readUInt32BE(at) !== trackId) throw new Error("A fragment belongs to another track");
    at += 4;
    let base = moof.start;
    if (flags & 0x1) {
      base = Number(buffer.readBigUInt64BE(at));
      at += 8;
    }
    if (flags & 0x2) {
      if (buffer.readUInt32BE(at) !== 1) throw new Error("Only one sample description is supported");
      at += 4;
    }
    const field = (present, fallback) => {
      if (!present) return fallback;
      at += 4;
      return buffer.readUInt32BE(at - 4);
    };
    const defaultDuration = field(flags & 0x8, trex.duration);
    const defaultSize = field(flags & 0x10, trex.size);
    const defaultFlags = field(flags & 0x20, trex.flags);
    const tfdt = child(buffer, traf, "tfdt");
    if (tfdt) {
      const base64 = buffer[tfdt.body] === 1;
      const start = base64 ? Number(buffer.readBigUInt64BE(tfdt.body + 4)) : buffer.readUInt32BE(tfdt.body + 4);
      if (decodeTime !== null && start !== decodeTime && samples.length > 0) {
        // A recorder writes a fragment before it knows how long its last frame lasts, so that duration is a guess
        // (MediaRecorder writes one frame period). The next fragment's decode time is the truth: the last frame
        // lasts until it, whether that is longer or shorter than the guess.
        const corrected = samples.at(-1).duration + start - decodeTime;
        if (corrected <= 0) throw new Error(`Fragment decode times overlap at ${start}`);
        samples.at(-1).duration = corrected;
      }
      decodeTime = start;
    }
    // A run without a data offset continues where the previous run of this fragment ended.
    let nextOffset = base;
    for (const trun of readBoxes(buffer, traf.body, traf.end).filter((item) => item.type === "trun")) {
      const version = buffer[trun.body];
      const runFlags = buffer.readUIntBE(trun.body + 1, 3);
      const count = buffer.readUInt32BE(trun.body + 4);
      let cursor = trun.body + 8;
      let dataOffset = 0;
      if (runFlags & 0x1) {
        dataOffset = buffer.readInt32BE(cursor);
        cursor += 4;
      }
      let firstFlags = null;
      if (runFlags & 0x4) {
        firstFlags = buffer.readUInt32BE(cursor);
        cursor += 4;
      }
      let offset = runFlags & 0x1 ? base + dataOffset : nextOffset;
      const chunk = { offset, size: 0, samples: 0 };
      for (let index = 0; index < count; index += 1) {
        const read = (present, signed = false) => {
          if (!present) return null;
          cursor += 4;
          return signed ? buffer.readInt32BE(cursor - 4) : buffer.readUInt32BE(cursor - 4);
        };
        const duration = read(runFlags & 0x100) ?? defaultDuration;
        const size = read(runFlags & 0x200) ?? defaultSize;
        const sampleFlags = read(runFlags & 0x400) ?? (index === 0 && firstFlags !== null ? firstFlags : defaultFlags);
        const composition = read(runFlags & 0x800, version === 1) ?? 0;
        if (offset + size > buffer.length) throw new Error("A sample runs past the end of the file");
        samples.push({ offset, size, duration, sync: (sampleFlags & NON_SYNC) === 0, composition });
        offset += size;
        chunk.size += size;
        chunk.samples += 1;
        decodeTime = (decodeTime ?? 0) + duration;
      }
      nextOffset = offset;
      if (chunk.samples > 0) chunks.push(chunk);
    }
  }
  if (samples.length === 0) throw new Error("The MP4 holds no fragments; it is not a fragmented recording");
  return { samples, chunks };
}

/**
 * Convert a fragmented single-track MP4 to a progressive one.
 * @param {Buffer} input
 * @returns {{ bytes: Buffer, seconds: number, samples: number, syncSamples: number, timescale: number }}
 */
export function progressiveMp4(input) {
  const top = readBoxes(input);
  const ftyp = need(top.find((item) => item.type === "ftyp"), "ftyp");
  const moov = need(top.find((item) => item.type === "moov"), "moov");
  if (top.indexOf(ftyp) !== 0) throw new Error("The MP4 must start with ftyp");
  const moovChildren = readBoxes(input, moov.body, moov.end);
  const traks = moovChildren.filter((item) => item.type === "trak");
  if (traks.length !== 1) throw new Error(`Expected one track, found ${traks.length}`);
  const trak = traks[0];
  const mvhd = need(child(input, moov, "mvhd"), "mvhd");
  const tkhd = need(child(input, trak, "tkhd"), "tkhd");
  const mdia = need(child(input, trak, "mdia"), "mdia");
  const mdhd = need(child(input, mdia, "mdhd"), "mdhd");
  const minf = need(child(input, mdia, "minf"), "minf");
  const stbl = need(child(input, minf, "stbl"), "stbl");
  const stsd = need(child(input, stbl, "stsd"), "stsd");
  const trackId = input.readUInt32BE(tkhd.body + (input[tkhd.body] === 1 ? 20 : 12));
  const mvex = child(input, moov, "mvex");
  const trexBox = mvex ? readBoxes(input, mvex.body, mvex.end).find((item) => item.type === "trex" && input.readUInt32BE(item.body + 4) === trackId) : null;
  const trex = trexBox
    ? { duration: input.readUInt32BE(trexBox.body + 12), size: input.readUInt32BE(trexBox.body + 16), flags: input.readUInt32BE(trexBox.body + 20) }
    : { duration: 0, size: 0, flags: 0 };

  const { samples, chunks } = fragmentSamples(input, top, trackId, trex);
  const mediaTimescale = timescaleOf(input, mdhd, { v0: 12, v1: 20 });
  const movieTimescale = timescaleOf(input, mvhd, { v0: 12, v1: 20 });
  const mediaDuration = samples.reduce((sum, sample) => sum + sample.duration, 0);
  const movieDuration = Math.round((mediaDuration * movieTimescale) / mediaTimescale);

  const sttsEntries = runs(samples.map((sample) => sample.duration));
  const compositions = samples.map((sample) => sample.composition);
  const cttsEntries = compositions.some((value) => value !== 0) ? runs(compositions) : null;
  const syncNumbers = samples.flatMap((sample, index) => (sample.sync ? [index + 1] : []));
  const stscEntries = [];
  chunks.forEach((chunk, index) => {
    if (stscEntries.at(-1)?.[1] !== chunk.samples) stscEntries.push([index + 1, chunk.samples, 1]);
  });
  const tables = (chunkOffsets) => box("stbl",
    input.subarray(stsd.start, stsd.end),
    fullBox("stts", 0, 0, u32(sttsEntries.length), ...sttsEntries.map(([count, delta]) => u32(count, delta))),
    ...(cttsEntries
      ? [fullBox("ctts", cttsEntries.some(([, value]) => value < 0) ? 1 : 0, 0, u32(cttsEntries.length), ...cttsEntries.map(([count, value]) => u32(count, value)))]
      : []),
    ...(syncNumbers.length < samples.length ? [fullBox("stss", 0, 0, u32(syncNumbers.length), u32(...syncNumbers))] : []),
    fullBox("stsc", 0, 0, u32(stscEntries.length), ...stscEntries.map((entry) => u32(...entry))),
    fullBox("stsz", 0, 0, u32(0, samples.length), u32(...samples.map((sample) => sample.size))),
    fullBox("stco", 0, 0, u32(chunkOffsets.length), u32(...chunkOffsets)),
  );
  const minfOthers = readBoxes(input, minf.body, minf.end).filter((item) => item.type !== "stbl").map((item) => input.subarray(item.start, item.end));
  const mdiaOthers = readBoxes(input, mdia.body, mdia.end).filter((item) => item.type !== "mdhd" && item.type !== "minf").map((item) => input.subarray(item.start, item.end));
  // An edit list written for the fragments would cut or shift the rewritten track, so it is left out: the track starts at 0.
  const trakOthers = readBoxes(input, trak.body, trak.end).filter((item) => !["tkhd", "mdia", "edts"].includes(item.type)).map((item) => input.subarray(item.start, item.end));
  const moovOthers = moovChildren.filter((item) => !["mvhd", "trak", "mvex"].includes(item.type)).map((item) => input.subarray(item.start, item.end));
  const buildMoov = (chunkOffsets) => box("moov",
    withDuration(input, mvhd, movieDuration, { v0: 16, v1: 24 }),
    box("trak",
      withDuration(input, tkhd, movieDuration, { v0: 20, v1: 28 }),
      ...trakOthers,
      box("mdia",
        withDuration(input, mdhd, mediaDuration, { v0: 16, v1: 24 }),
        ...mdiaOthers,
        box("minf", ...minfOthers, tables(chunkOffsets)))),
    ...moovOthers);
  const newFtyp = box("ftyp", Buffer.from("isom", "latin1"), u32(0x200), Buffer.from("isomiso2avc1mp41", "latin1"));
  // The moov's size does not depend on the offsets' values, so measure it once with placeholders.
  const moovSize = buildMoov(chunks.map(() => 0)).length;
  const mdatPayload = chunks.reduce((sum, chunk) => sum + chunk.size, 0);
  if (newFtyp.length + moovSize + 8 + mdatPayload > 0xffffffff) throw new Error("Files over 4 GB are not supported");
  let cursor = newFtyp.length + moovSize + 8;
  const offsets = chunks.map((chunk) => {
    const offset = cursor;
    cursor += chunk.size;
    return offset;
  });
  const mdatHeader = Buffer.alloc(8);
  mdatHeader.writeUInt32BE(8 + mdatPayload, 0);
  mdatHeader.write("mdat", 4, "latin1");
  const bytes = Buffer.concat([newFtyp, buildMoov(offsets), mdatHeader, ...chunks.map((chunk) => input.subarray(chunk.offset, chunk.offset + chunk.size))]);
  return { bytes, seconds: mediaDuration / mediaTimescale, samples: samples.length, syncSamples: syncNumbers.length, timescale: mediaTimescale };
}
