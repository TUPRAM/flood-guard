import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve, sep } from "node:path";
import { test } from "node:test";
import { gzipSync } from "node:zlib";
import { auditGzipJson } from "./evidence-gzip-json-audit.mjs";

async function auditFixture(contents, options) {
  const directory = mkdtempSync(resolve(tmpdir(), "floodguard-gzip-audit-test-"));
  const path = resolve(directory, "download.json.gz");
  try {
    writeFileSync(path, gzipSync(contents));
    return await auditGzipJson(path, options);
  } finally {
    if (!resolve(directory).startsWith(`${resolve(tmpdir())}${sep}floodguard-gzip-audit-test-`)) throw new Error("Unsafe test cleanup target");
    rmSync(directory, { recursive: true, force: true });
  }
}

test("streams a valid large JSON document with strings crossing decompression chunks", async () => {
  const document = JSON.stringify({ rows: [{ summary: "ใช้ข้อมูลสาธารณะ" }, { values: Array.from({ length: 55_000 }, (_, i) => i) }] });
  assert.equal(await auditFixture(document), Buffer.byteLength(document));
});

test("rejects escaped private keys and local paths in a compressed derivative", async () => {
  await assert.rejects(auditFixture('{"\\u0061pi_key":"secret"}'), /Private\/raw field/);
  await assert.rejects(auditFixture('{"context":"C:\\\\Users\\\\private\\\\raw.csv"}'), /Local filesystem path/);
});

test("rejects malformed JSON even when gzip integrity is valid", async () => {
  for (const invalid of ['{"rows":[1,2,]}', '{"rows":true} garbage', '{"a":\u00a01}', '{"rows":[1,2}']) {
    await assert.rejects(auditFixture(invalid), /Invalid public evidence JSON/);
  }
});

test("rejects invalid UTF-8 and an inflated document over its configured limit", async () => {
  await assert.rejects(auditFixture(Buffer.from([0x7b, 0x22, 0xff, 0x22, 0x7d])), /encoded data|valid for encoding/i);
  await assert.rejects(auditFixture(JSON.stringify({ pad: "x".repeat(1024) }), { maxOutputBytes: 100 }), /exceeds 100 inflated bytes/);
});
