import { createReadStream } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createGunzip } from "node:zlib";
import { assertPublicEvidenceKey, assertPublicEvidenceText } from "./evidence-library-assets.mjs";

// The largest cleared archive currently expands to 588,903,070 bytes. Keep
// decompression bounded without holding that JSON or its parsed tree in memory.
export const MAX_INFLATED_BYTES = 640 * 1024 * 1024;
const MAX_STRING_CHARS = 16 * 1024 * 1024;
const MAX_SCALAR_CHARS = 256;
const MAX_DEPTH = 128;
const NUMBER = /^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?$/u;
const isWhitespace = (char) => char === " " || char === "\n" || char === "\r" || char === "\t";

class PublicJsonAudit {
  constructor() {
    this.stack = [];
    this.rootState = "value";
    this.mode = null;
    this.tokenParts = [];
    this.tokenChars = 0;
    this.escape = false;
    this.stringRole = null;
  }

  fail(reason) { throw new Error(`Invalid public evidence JSON: ${reason}`); }

  state() { return this.stack.at(-1)?.state ?? this.rootState; }

  appendToken(piece) {
    this.tokenChars += piece.length;
    const limit = this.mode === "string" ? MAX_STRING_CHARS : MAX_SCALAR_CHARS;
    if (this.tokenChars > limit) this.fail("token exceeds bounded audit limit");
    this.tokenParts.push(piece);
  }

  takeToken(piece) {
    this.appendToken(piece);
    const raw = this.tokenParts.join("");
    this.tokenParts = [];
    this.tokenChars = 0;
    this.mode = null;
    return raw;
  }

  completeValue() {
    const frame = this.stack.at(-1);
    if (!frame) {
      if (this.rootState !== "value") this.fail("extra root value");
      this.rootState = "end";
    } else if (frame.state === "value" || frame.state === "value_or_end") frame.state = "comma_or_end";
    else this.fail("value in unexpected position");
  }

  closeContainer(type) {
    const frame = this.stack.at(-1);
    if (frame?.type !== type) this.fail("mismatched container close");
    this.stack.pop();
    this.completeValue();
  }

  beginString(role, start) {
    this.mode = "string";
    this.stringRole = role;
    this.escape = false;
    return start + 1;
  }

  finishString(raw) {
    let value;
    try { value = JSON.parse(raw); } catch { this.fail("malformed string"); }
    assertPublicEvidenceText(value);
    if (this.stringRole === "key") {
      assertPublicEvidenceKey(value);
      this.stack.at(-1).state = "colon";
    } else this.completeValue();
    this.stringRole = null;
  }

  finishScalar(raw) {
    if (!["true", "false", "null"].includes(raw) && (!NUMBER.test(raw) || !Number.isFinite(Number(raw)))) {
      this.fail("malformed scalar");
    }
    this.completeValue();
  }

  feed(text) {
    let i = 0;
    let tokenStart = this.mode ? 0 : -1;
    while (i < text.length) {
      if (this.mode === "string") {
        const char = text[i];
        if (this.escape) this.escape = false;
        else if (char === "\\") this.escape = true;
        else if (char === '"') {
          const raw = this.takeToken(text.slice(tokenStart, i + 1));
          this.finishString(raw);
          tokenStart = -1;
        }
        i += 1;
        continue;
      }
      if (this.mode === "scalar") {
        const char = text[i];
        if (isWhitespace(char) || char === "," || char === "]" || char === "}") {
          const raw = this.takeToken(text.slice(tokenStart, i));
          this.finishScalar(raw);
          tokenStart = -1;
          continue;
        }
        i += 1;
        continue;
      }

      const char = text[i];
      if (isWhitespace(char)) { i += 1; continue; }
      const frame = this.stack.at(-1);
      const state = this.state();
      if (state === "key_or_end" || state === "key") {
        if (char === "}" && state === "key_or_end") { this.closeContainer("object"); i += 1; continue; }
        if (char !== '"') this.fail("expected object key");
        tokenStart = i;
        i = this.beginString("key", i);
        continue;
      }
      if (state === "colon") {
        if (char !== ":") this.fail("expected colon");
        frame.state = "value";
        i += 1;
        continue;
      }
      if (state === "comma_or_end") {
        if (char === ",") { frame.state = frame.type === "object" ? "key" : "value"; i += 1; continue; }
        if (char === (frame.type === "object" ? "}" : "]")) { this.closeContainer(frame.type); i += 1; continue; }
        this.fail("expected comma or container close");
      }
      if (state === "value_or_end" && char === "]") { this.closeContainer("array"); i += 1; continue; }
      if (state !== "value" && state !== "value_or_end") this.fail("extra content after root value");
      if (char === "{" || char === "[") {
        if (this.stack.length >= MAX_DEPTH) this.fail("nesting exceeds bounded audit limit");
        this.stack.push({ type: char === "{" ? "object" : "array", state: char === "{" ? "key_or_end" : "value_or_end" });
        i += 1;
        continue;
      }
      if (char === '"') {
        tokenStart = i;
        i = this.beginString("value", i);
        continue;
      }
      if (!/[-0-9tfn]/u.test(char)) this.fail("expected value");
      this.mode = "scalar";
      tokenStart = i;
    }
    if (this.mode) this.appendToken(text.slice(tokenStart));
  }

  finish() {
    if (this.mode === "scalar") this.finishScalar(this.takeToken(""));
    if (this.mode || this.stack.length || this.rootState !== "end") this.fail("truncated JSON");
  }
}

/** Audit one gzip JSON download without materializing its expanded contents. */
export async function auditGzipJson(path, { maxOutputBytes = MAX_INFLATED_BYTES } = {}) {
  const source = createReadStream(path);
  const inflated = createGunzip({ chunkSize: 256 * 1024 });
  source.on("error", (error) => inflated.destroy(error));
  source.pipe(inflated);
  const decoder = new TextDecoder("utf-8", { fatal: true });
  const audit = new PublicJsonAudit();
  let expandedBytes = 0;
  try {
    for await (const chunk of inflated) {
      expandedBytes += chunk.length;
      if (expandedBytes > maxOutputBytes) throw new Error(`Evidence gzip JSON exceeds ${maxOutputBytes} inflated bytes`);
      audit.feed(decoder.decode(chunk, { stream: true }));
    }
    audit.feed(decoder.decode());
    audit.finish();
    return expandedBytes;
  } finally {
    source.destroy();
    inflated.destroy();
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  auditGzipJson(process.argv[2]).catch((error) => {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  });
}
