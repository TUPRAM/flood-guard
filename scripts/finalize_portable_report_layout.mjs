#!/usr/bin/env node

/** Apply a bounded layout fix to a generated self-contained analytics report.
 *
 * The packaged report reader uses a 100vw top bar. On browsers whose vertical
 * scrollbar consumes layout width, that creates a small page-level horizontal
 * overflow even though the report content itself fits. This finalizer changes
 * only the top-bar width/margins; it does not alter the embedded artifact,
 * metrics, sources, charts, or report copy.
 */

import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const STYLE_ID = "floodguard-portable-report-layout-fix";
const STYLE = `<style id="${STYLE_ID}">
.analytics-top-bar,
.portable-page-header {
  width: 100% !important;
  margin-right: 0 !important;
  margin-left: 0 !important;
}
</style>`;

function usage() {
  return "Usage: node scripts/finalize_portable_report_layout.mjs <input.html> <output.html>";
}

function main(argv) {
  if (argv.length !== 2) {
    throw new Error(usage());
  }
  const [inputPath, outputPath] = argv.map((value) => resolve(value));
  if (inputPath === outputPath) {
    throw new Error("Input and output must be different paths.");
  }
  const html = readFileSync(inputPath, "utf8");
  if (!html.includes("</head>")) {
    throw new Error("Generated report is missing </head>.");
  }
  if (html.includes(`id="${STYLE_ID}"`)) {
    throw new Error("Generated report already contains the FloodGuard layout fix.");
  }
  const finalized = html.replace("</head>", `${STYLE}\n</head>`);
  writeFileSync(outputPath, finalized, { encoding: "utf8", flag: "wx" });
  process.stdout.write(`Wrote finalized portable report: ${outputPath}\n`);
}

try {
  main(process.argv.slice(2));
} catch (error) {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
}
