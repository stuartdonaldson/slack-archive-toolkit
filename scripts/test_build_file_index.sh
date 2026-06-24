#!/usr/bin/env bash
# Tests for build-file-index.sh and scripts/lib/file_index_helpers.sh.
# Fully fixture-driven (hand-built minimal slackdump.sqlite fixtures), no
# live slackdump/API calls.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/file_index_helpers.sh"

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

FAILED=0

assert_eq() {
    local name="$1" expected="$2" actual="$3"
    if [[ "$expected" == "$actual" ]]; then
        echo "PASS: $name"
    else
        echo "FAIL: $name" >&2
        echo "  expected: $expected" >&2
        echo "  actual:   $actual" >&2
        FAILED=1
    fi
}

# --- sanitize_filename: pure-function checks against nasty inputs ---

assert_eq "sanitize: plain name unchanged" "report.pdf" "$(sanitize_filename "report.pdf")"
assert_eq "sanitize: path separators replaced" "a_b_c.txt" "$(sanitize_filename "a/b/c.txt")"
assert_eq "sanitize: leading dots/spaces stripped" "hidden" "$(sanitize_filename "  .hidden")"
assert_eq "sanitize: shell/Windows-unsafe punctuation replaced" "weird_name_.jpg" "$(sanitize_filename "weird:name?.jpg")"
assert_eq "sanitize: embedded tab/control chars replaced" "tab_here.png" "$(sanitize_filename "$(printf 'tab\there.png')")"
assert_eq "sanitize: unicode preserved" "très_long_ñame.pdf" "$(sanitize_filename "très_long_ñame.pdf")"
assert_eq "sanitize: empty input falls back to underscore" "_" "$(sanitize_filename "")"

# --- file_index_merge: pure cross-source dedupe/aggregation ---

EXISTING='[]'
ARCHIVE_FIRST='[{"id":"F1","first_seen":"2026-01-01 00:00:00","last_seen":"2026-01-01 00:00:00","local_path":"/archive/F1"}]'
M1="$(file_index_merge "$EXISTING" "$ARCHIVE_FIRST")"
SEARCH_LATER='[{"id":"F1","first_seen":"2026-02-01 00:00:00","last_seen":"2026-02-01 00:00:00","local_path":"/search/F1"}]'
M2="$(file_index_merge "$M1" "$SEARCH_LATER")"

assert_eq "merge: earlier-processed source's local_path wins on collision" \
    "/archive/F1" "$(jq -r '.[0].local_path' <<< "$M2")"
assert_eq "merge: first_seen/last_seen aggregate across both sources" \
    "2026-01-01 00:00:00 2026-02-01 00:00:00" \
    "$(jq -r '.[0].first_seen + " " + .[0].last_seen' <<< "$M2")"

# --- build-file-index.sh end to end, against hand-built fixture dbs ---

ARCHIVE_ROOT="$WORKDIR/archive"
SEARCH_ROOT="$WORKDIR/search"
OUT_FILES="$WORKDIR/files"
INDEX_JSON="$WORKDIR/index.json"
CHANNEL_DIR="$ARCHIVE_ROOT/f3test/general"
TERM_DIR="$SEARCH_ROOT/f3test/term1"
mkdir -p "$CHANNEL_DIR/__uploads/FA1" "$CHANNEL_DIR/__uploads/FA2" \
         "$CHANNEL_DIR/__uploads/FA3" "$CHANNEL_DIR/__uploads/FSHARED" \
         "$TERM_DIR/__uploads/FSHARED" "$TERM_DIR/__uploads/FS2"

echo "canvas content" > "$CHANNEL_DIR/__uploads/FA1/TeamCanvas"
echo "pdf content" > "$CHANNEL_DIR/__uploads/FA2/doc.pdf"
echo "image content" > "$CHANNEL_DIR/__uploads/FA3/photo.png"
echo "shared content" > "$CHANNEL_DIR/__uploads/FSHARED/shared.docx"
echo "shared content" > "$TERM_DIR/__uploads/FSHARED/shared.docx"
echo "new content" > "$TERM_DIR/__uploads/FS2/newfile.txt"

sqlite3 "$CHANNEL_DIR/slackdump.sqlite" <<'SQL'
CREATE TABLE FILE (ID TEXT, CHUNK_ID INTEGER, LOAD_DTTM TIMESTAMP, CHANNEL_ID TEXT, MESSAGE_ID INTEGER, FILENAME TEXT, SIZE INTEGER, DATA TEXT);
CREATE TABLE MESSAGE (ID INTEGER, CHUNK_ID INTEGER, CHANNEL_ID TEXT, TS TEXT);

INSERT INTO FILE VALUES ('FA1', 1, '2026-01-01 00:00:00', 'CGEN1', NULL, 'TeamCanvas', 14,
  '{"id":"FA1","name":"TeamCanvas","title":"Team Canvas","mimetype":"application/vnd.slack-docs","filetype":"quip","created":1700000000,"permalink":"https://x/FA1"}');
INSERT INTO FILE VALUES ('FA1', 2, '2026-01-05 00:00:00', 'CGEN1', NULL, 'TeamCanvas', 14,
  '{"id":"FA1","name":"TeamCanvas","title":"Team Canvas","mimetype":"application/vnd.slack-docs","filetype":"quip","created":1700000000,"permalink":"https://x/FA1"}');

INSERT INTO FILE VALUES ('FA2', 1, '2026-01-02 00:00:00', 'CGEN1', 1700000100000000, 'doc.pdf', 11,
  '{"id":"FA2","name":"doc.pdf","title":"doc","mimetype":"application/pdf","filetype":"pdf","created":1700000100,"permalink":"https://x/FA2"}');
INSERT INTO MESSAGE VALUES (1700000100000000, 1, 'CGEN1', '1700000100.000000');

INSERT INTO FILE VALUES ('FA3', 1, '2026-01-02 00:00:00', 'CGEN1', NULL, 'photo.png', 9,
  '{"id":"FA3","name":"photo.png","title":"photo","mimetype":"image/png","filetype":"png","created":1700000200,"permalink":"https://x/FA3"}');

INSERT INTO FILE VALUES ('FSHARED', 1, '2026-01-03 00:00:00', 'CGEN1', NULL, 'shared.docx', 14,
  '{"id":"FSHARED","name":"shared.docx","title":"Shared","mimetype":"application/msword","filetype":"docx","created":1700000300,"permalink":"https://x/FSHARED"}');
SQL

sqlite3 "$TERM_DIR/slackdump.sqlite" <<'SQL'
CREATE TABLE FILE (ID TEXT, CHUNK_ID INTEGER, LOAD_DTTM TIMESTAMP, CHANNEL_ID TEXT, MESSAGE_ID INTEGER, FILENAME TEXT, SIZE INTEGER, DATA TEXT);
CREATE TABLE MESSAGE (ID INTEGER, CHUNK_ID INTEGER, CHANNEL_ID TEXT, TS TEXT);

INSERT INTO FILE VALUES ('FSHARED', 1, '2026-02-01 00:00:00', 'SEARCH', NULL, 'shared.docx', 14,
  '{"id":"FSHARED","name":"shared.docx","title":"Shared","mimetype":"application/msword","filetype":"docx","created":1700000300,"permalink":"https://x/FSHARED","channels":["CGEN1"]}');

INSERT INTO FILE VALUES ('FS2', 1, '2026-02-02 00:00:00', 'SEARCH', NULL, 'newfile.txt', 12,
  '{"id":"FS2","name":"newfile.txt","title":"New File","mimetype":"text/plain","filetype":"text","created":1700000400,"permalink":"https://x/FS2","channels":["CNEW1"]}');
SQL

CATALOG_CACHE_DIR="$WORKDIR/cache"
mkdir -p "$CATALOG_CACHE_DIR"
printf 'CGEN1\tyes\tgeneral\tGeneral channel\n' > "$CATALOG_CACHE_DIR/f3test.catalog.tsv"
export CATALOG_CACHE_DIR

OUTPUT1="$("$SCRIPT_DIR/build-file-index.sh" "$OUT_FILES" "$INDEX_JSON" \
    --archive-root "$ARCHIVE_ROOT" --search-root "$SEARCH_ROOT" 2>&1)"

assert_eq "build: image file excluded from index" \
    "" "$(jq -r '.[] | select(.id == "FA3")' "$INDEX_JSON")"

assert_eq "build: canvas included with channel_canvas context" \
    "channel_canvas" "$(jq -r '.[] | select(.id == "FA1") | .message_context.type' "$INDEX_JSON")"

assert_eq "build: canvas first/last seen aggregated across its two FILE rows" \
    "2026-01-01 00:00:00 2026-01-05 00:00:00" \
    "$(jq -r '.[] | select(.id == "FA1") | .first_seen + " " + .last_seen' "$INDEX_JSON")"

assert_eq "build: message attachment resolves ts via MESSAGE join" \
    "message_attachment 1700000100.000000" \
    "$(jq -r '.[] | select(.id == "FA2") | .message_context.type + " " + .message_context.ts' "$INDEX_JSON")"

assert_eq "build: tracked-channel name comes from the archive directory path" \
    "general" "$(jq -r '.[] | select(.id == "FA1") | .channel' "$INDEX_JSON")"

assert_eq "build: search-result channel resolved via catalog by real channel id" \
    "general" "$(jq -r '.[] | select(.id == "FSHARED") | .channel' "$INDEX_JSON")"

assert_eq "build: search-result channel falls back to raw id when uncataloged" \
    "CNEW1" "$(jq -r '.[] | select(.id == "FS2") | .channel' "$INDEX_JSON")"

assert_eq "build: cross-source duplicate copied once, under the archive's (earlier-processed) channel name" \
    "$OUT_FILES/f3test/general/shared__FSHARED.docx" \
    "$(jq -r '.[] | select(.id == "FSHARED") | .local_path' "$INDEX_JSON")"

if [[ -f "$OUT_FILES/f3test/general/TeamCanvas__FA1" ]]; then
    echo "PASS: build: canvas blob copied to sanitized destination path"
else
    echo "FAIL: build: expected canvas blob at $OUT_FILES/f3test/general/TeamCanvas__FA1" >&2
    FAILED=1
fi

assert_eq "build: total indexed entries (FA1, FA2, FSHARED, FS2 - FA3 excluded)" \
    "4" "$(jq 'length' "$INDEX_JSON")"

# --- idempotent re-run: no new fixture data, everything should be skipped ---

OUTPUT2="$("$SCRIPT_DIR/build-file-index.sh" "$OUT_FILES" "$INDEX_JSON" \
    --archive-root "$ARCHIVE_ROOT" --search-root "$SEARCH_ROOT" 2>&1)"

if grep -q '^wrote ' <<< "$OUTPUT2"; then
    echo "FAIL: re-run should not re-write any entry, got:" >&2
    echo "$OUTPUT2" >&2
    FAILED=1
else
    echo "PASS: re-run reports no new writes"
fi

SKIPPED_COUNT="$(grep -c '^skipped (exists)' <<< "$OUTPUT2" || true)"
assert_eq "re-run: every entry reported as skipped" "4" "$SKIPPED_COUNT"

assert_eq "re-run: index.json entry count unchanged" "4" "$(jq 'length' "$INDEX_JSON")"

exit "$FAILED"
