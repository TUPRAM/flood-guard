"""Run a non-test verification command and record its exit status as JUnit XML."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET


def run_check(suite: str, output: Path, command: list[str]) -> int:
    """Run one reviewed command, stream output, and atomically write a JUnit receipt."""

    if not suite.strip():
        raise ValueError("suite must be a non-empty string.")
    if not command or not command[0].strip():
        raise ValueError("command must not be empty.")
    executable = shutil.which(command[0])
    if executable is None:
        raise FileNotFoundError(f"Verification executable is unavailable: {command[0]}")
    invoked = [executable, *command[1:]]
    started_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    started = time.monotonic()
    completed = subprocess.run(invoked, check=False)
    elapsed = time.monotonic() - started

    testsuite = ET.Element(
        "testsuite",
        {
            "name": suite,
            "tests": "1",
            "failures": "1" if completed.returncode else "0",
            "errors": "0",
            "skipped": "0",
            "time": f"{elapsed:.6f}",
            "timestamp": started_at,
        },
    )
    testcase = ET.SubElement(
        testsuite,
        "testcase",
        {
            "classname": "proposal.verification",
            "name": suite,
            "time": f"{elapsed:.6f}",
        },
    )
    if completed.returncode:
        failure = ET.SubElement(
            testcase,
            "failure",
            {"message": f"Command exited with status {completed.returncode}"},
        )
        failure.text = "The command output was streamed to the build log."
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    ET.ElementTree(testsuite).write(temporary, encoding="utf-8", xml_declaration=True)
    temporary.replace(output)
    return completed.returncode


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for one command-to-JUnit receipt."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    return run_check(args.suite, args.output, command)


if __name__ == "__main__":
    raise SystemExit(main())
