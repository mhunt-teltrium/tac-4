# Feature: JSONL Support

## Feature Description
Allow users to upload `.jsonl` (JSON Lines) files alongside `.csv` and `.json`. Each JSONL file produces exactly one SQLite table. The whole file is scanned first to discover every possible field (records may have differing keys), nested objects and lists are flattened into columns by concatenating path segments with an updatable delimiter (default `__`), and list items are denoted by their index (`tags__0`, `tags__1`). Only the Python standard library is used for parsing/flattening (pandas, already a dependency, is still used for writing to SQLite, as in the existing converters).

## User Story
As a data analyst
I want to upload JSONL files and query them with natural language
So that I can work with log/event/export data without converting it to CSV or JSON first

## Problem Statement
JSONL is a common export format for logs, LLM datasets, and streaming data, but the app only accepts `.csv` and `.json`. JSONL records often have nested objects, lists, and inconsistent keys across lines, so a naive line-by-line load would miss columns.

## Solution Statement
Add `convert_jsonl_to_sqlite` in `core/file_processor.py`. Pass 1 parses every line and flattens each record to a `{column: value}` dict; the ordered union of all keys (first-seen order) becomes the column set. Pass 2 builds a DataFrame with that full column set (missing values -> NULL) and writes it to SQLite, then returns schema/row count/sample data identically to the existing converters. The delimiter lives in a new constants module (`core/constants.py`, `NESTED_FIELD_DELIMITER = "__"`). Server upload endpoint and UI text are updated to accept `.jsonl`.

## Relevant Files
Use these files to implement the feature:

- `README.md` - Mentions supported upload types; update.
- `app/server/core/file_processor.py` - Contains the csv/json converters and `sanitize_table_name`; add the JSONL converter and flatten helpers here.
- `app/server/server.py` - `/api/upload` validates extensions and dispatches converters; add `.jsonl`.
- `app/server/tests/core/test_file_processor.py` - Existing converter tests; add JSONL tests.
- `app/server/tests/assets/` - Existing test fixtures location.
- `app/client/index.html` - Upload drop-zone text and `accept` attribute (lines ~80-81).
- `app/client/src/main.ts` - Upload handling; verify no client-side extension filtering needs changing.

### New Files
- `app/server/core/constants.py` - `NESTED_FIELD_DELIMITER = "__"` (single place to change the delimiter).
- `app/server/tests/assets/test_events.jsonl` - Nested objects, lists, and inconsistent keys across lines.
- `app/server/tests/assets/test_simple.jsonl` - Flat records.
- `app/server/tests/assets/invalid.jsonl` - Contains a malformed line (error-path test).

## Implementation Plan
### Phase 1: Foundation
Create `core/constants.py` with the delimiter. Create the JSONL test assets.

### Phase 2: Core Implementation
In `file_processor.py` add:
- `_flatten_record(value, prefix="", delimiter=NESTED_FIELD_DELIMITER) -> Dict[str, Any]`: recursively flattens dicts (key joined by delimiter) and lists (index joined by delimiter, e.g. `items__0__name`, `tags__0`). Scalars/None are leaves. Empty dict/list yields the key with `None` so the field is still discovered.
- `convert_jsonl_to_sqlite(jsonl_content: bytes, table_name: str)`: decode UTF-8 (`utf-8-sig`), skip blank lines, `json.loads` each line with line-numbered errors, require each line to be a JSON object, flatten, collect the ordered union of all columns across the whole file, build rows, create `pd.DataFrame(rows, columns=all_columns)`, clean column names the same way as the other converters (lower, spaces/hyphens -> `_`), write with `to_sql(if_exists='replace')`, and return the same result dict. Error wrapped as `Error converting JSONL to SQLite: ...`. Raise on empty file. Handle post-cleaning column name collisions by suffixing.

### Phase 3: Integration
Update `/api/upload` to accept `.jsonl` (case-sensitive consistent with existing behavior; check `.jsonl` before generic handling), error message "Only .csv, .json, and .jsonl files are supported", and dispatch to the new converter. Update UI text and `accept`. Update README.

## Step by Step Tasks
IMPORTANT: Execute every step in order, top to bottom.

### Add constants module
- Create `app/server/core/constants.py` with `NESTED_FIELD_DELIMITER = "__"`.

### Create test assets
- `test_events.jsonl`: ~4 lines; include nested object (`user.name`, `user.address.city`), list of scalars (`tags`), list of objects (`items`), and keys present only in some lines (e.g. `error_code` only on line 3, `metadata.region` only on line 4).
- `test_simple.jsonl`: 3 flat records (id, name, price).
- `invalid.jsonl`: one valid line, one malformed line.

### Implement converter
- Add `_flatten_record` and `convert_jsonl_to_sqlite` in `file_processor.py` per Phase 2, importing the delimiter from `.constants`. Use only stdlib (`json`) for parsing/flattening.

### Wire up server
- Import the converter in `server.py`; accept `.jsonl`; dispatch by extension; update docstring and error message.

### Update UI and docs
- `index.html`: text "Drag and drop .csv, .json, or .jsonl files here"; `accept=".csv,.json,.jsonl"`.
- Check `main.ts` for any extension-specific messaging and update if present.
- README feature bullet: `.csv`, `.json`, and `.jsonl`; briefly document flattening (`__` delimiter, `_0` style list indexes, configurable in `core/constants.py`).

### Add tests
- In `test_file_processor.py` add tests (using existing `test_db` fixture and assets) for the cases listed under Testing Strategy.

### Run validation commands
- Run all commands under Validation Commands.

## Testing Strategy
### Unit Tests
- Flat JSONL loads: correct table name, columns, row count.
- Nested objects flatten to `user__name`, `user__address__city`.
- Lists flatten to `tags__0`, `tags__1`, `items__0__name`.
- Union of fields across all lines is present; missing values are NULL.
- Delimiter honors `NESTED_FIELD_DELIMITER` (monkeypatch the constant/parameter and verify).
- Malformed line raises error mentioning the line number.
- Empty file / only blank lines raises error.
- Non-object line (e.g. `[1,2]`) raises error.

### Integration Tests
- POST a `.jsonl` file to `/api/upload` and verify response schema, then query the table via `/api/query` path or SQLite directly.
- Uploading `.txt` still returns the unsupported-type error.

### Edge Cases
- Blank lines and trailing newline; CRLF line endings; UTF-8 BOM.
- Keys that differ only by case/spaces after cleaning (collision handling).
- Empty list/object values; null values; mixed types in a column.
- First line lacks fields that appear later (full-file scan).
- Deeply nested structures and large lists produce many columns.

## Acceptance Criteria
- `.jsonl` files upload via the UI (drag/drop and file picker) and create one table named after the file.
- Columns are the union of all fields in the entire file.
- Nested fields use the delimiter from `core/constants.py`; list items use `<field><delimiter><index>`.
- UI text states that `.jsonl` is supported.
- Test JSONL files exist under `app/server/tests/assets/`.
- No new dependencies are added; existing csv/json behavior is unchanged and all tests pass.

## Validation Commands
Execute every command to validate the feature works correctly with zero regressions.

- `cd app/server && uv run pytest` - Run server tests to validate the feature works with zero regressions
- `cd app/client && npm run build` - Validate the client builds (type-check) with zero regressions
- `cd app/server && uv run python -c "from core.file_processor import convert_jsonl_to_sqlite as c; print(c(open('tests/assets/test_events.jsonl','rb').read(),'events_check')['schema'])"` - Smoke test flattening (run from a directory with `db/`; remove the `events_check` table afterwards)

## Notes
- No new libraries; JSONL parsing/flattening uses stdlib `json`. pandas is already used for SQLite writes.
- Column names are lowercased by the shared cleaning step, so `Key` and `key` would collide; the converter must disambiguate.
- Very wide tables: SQLite's default column limit is 2000; surface a clear error if exceeded.
