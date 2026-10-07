# Validation check

A page for the three team members, at `/studio/validation-check/` on the competition site. It lists what the team is
asked to look at before a result goes on a page or into the pitch, and lets each member hand a record over.

**What a record is.** The word of a team member on the project's own work: `accept`, `change` or `reject`, with a
note. It is not a review by an independent expert, it qualifies no flood map, and it is not an official approval or
an official warning. The gates of the signed protocols are untouched by it.

**The rule.** An item is accepted when all three reviewers accept it. One `change` or `reject` holds it until that
reviewer accepts. For each item and reviewer the record received last counts.

## How a record travels

1. A reviewer opens the page, chooses a name, decides on the items whose evidence is ready, and adds a note to every
   decision that is not an acceptance. The draft stays in that browser.
2. The reviewer hands the record over:
   - **GitHub issue.** The page opens a new issue with the record in it and the label `validation-check`; the reviewer
     submits it. It counts when the issue comes from the account listed for that reviewer in `reviewers.json`.
   - **File or copied text.** For a reviewer without an account. A team member passes the file on.
3. A working session takes the records in:

   ```bash
   python scripts/import_validation_records.py --github
   ```

   ```bash
   python scripts/import_validation_records.py --file <path to the record file>
   ```

4. The script appends what is new to `acceptance_records.jsonl`, writes what it refused, with the reason, to
   `refused_records.jsonl`, and rewrites `STATUS.md` and the state file the page reads
   (`apps/web/src/lib/validation-check-records.json`). After the next deploy the page shows the new state.

## Files

| File | What it is |
|---|---|
| `apps/web/src/lib/validation-check-items.json` | The list of items. An item is added with `ready: false` while its evidence is being made, and set to `true` when there is something to look at |
| `reviewers.json` | The GitHub account whose issues count for each reviewer |
| `acceptance_records.jsonl` | Every record that counts, one per line, append-only |
| `refused_records.jsonl` | Records that were not counted, with the reasons |
| `STATUS.md` | The state as a table, written by the script |
| `src/floodguard/validation_records.py` | Parsing, checking and folding of records |
| `scripts/import_validation_records.py` | The import; `--check` fails when the state file does not match the log |

## Record text

```text
floodguard-validation-record v1
reviewer: Putu
recorded_at: 2026-10-07T09:00:00Z
V-01: accept
V-02: change | say what to change, on one line
```

## Limits

- The page is on the public competition site. Anyone can open it and read the list; nothing on it is secret. A record
  only counts through the two ways above.
- A record from a file is taken as stated.
- The page text is English only.
