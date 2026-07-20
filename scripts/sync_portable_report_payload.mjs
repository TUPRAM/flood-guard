#!/usr/bin/env node

/** Synchronize a portable report's embedded payload with its artifact JSON. */

import { readFileSync, writeFileSync } from "node:fs";
import { basename, resolve } from "node:path";
import { gzipSync } from "node:zlib";

const TEMPLATE_OPEN =
  '<template id="data-analytics-portable-artifact-payload-source" data-compression="gzip-base64">';
const TEMPLATE_CLOSE = "</template>";

function usage() {
  return "Usage: node scripts/sync_portable_report_payload.mjs <artifact.json> <report.html>";
}

function wrappedBase64(value) {
  return value.match(/.{1,76}/g)?.join("\n") ?? "";
}

function main(argv) {
  if (argv.length !== 2) {
    throw new Error(usage());
  }
  const artifactPath = resolve(argv[0]);
  const reportPath = resolve(argv[1]);
  const artifact = JSON.parse(readFileSync(artifactPath, "utf8"));
  for (const key of ["surface", "manifest", "snapshot", "sources"]) {
    if (!(key in artifact)) {
      throw new Error(`Artifact JSON is missing required field: ${key}`);
    }
  }

  const html = readFileSync(reportPath, "utf8");
  const openIndex = html.indexOf(TEMPLATE_OPEN);
  if (openIndex < 0 || html.indexOf(TEMPLATE_OPEN, openIndex + 1) >= 0) {
    throw new Error("Report must contain exactly one portable payload template.");
  }
  const payloadStart = openIndex + TEMPLATE_OPEN.length;
  const closeIndex = html.indexOf(TEMPLATE_CLOSE, payloadStart);
  if (closeIndex < 0) {
    throw new Error("Portable payload template is not closed.");
  }

  const payload = {
    surface: artifact.surface,
    manifest: artifact.manifest,
    snapshot: artifact.snapshot,
    sources: artifact.sources,
  };
  const compressed = gzipSync(Buffer.from(JSON.stringify(payload), "utf8"), {
    level: 9,
    mtime: 0,
  });
  const replacement = `\n${wrappedBase64(compressed.toString("base64"))}\n`;
  const synchronized =
    html.slice(0, payloadStart) + replacement + html.slice(closeIndex);
  writeFileSync(reportPath, synchronized, "utf8");
  process.stdout.write(`Synchronized embedded payload: ${basename(reportPath)}\n`);
}

try {
  main(process.argv.slice(2));
} catch (error) {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
}
