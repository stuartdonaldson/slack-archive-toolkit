# Sourced helper: pure-logic pieces of build-file-index.sh, split out for
# unit testing without needing real slackdump.sqlite fixtures for every case
# (sanitize_filename) or for testing the cross-source merge in isolation
# from sqlite (file_index_merge).

# sanitize_filename <name> -> filesystem-safe filename: strips path
# separators and other unsafe characters, collapses repeats, trims leading
# dots (hidden-file risk) and surrounding whitespace. Pure function.
sanitize_filename() {
    local name="$1"
    name="${name//\//_}"
    # Strip ASCII control chars and Windows/shell-unsafe punctuation, but
    # leave multi-byte UTF-8 sequences (e.g. accented/non-Latin names) alone.
    name="$(LC_ALL=C sed -E 's/[\x01-\x1f\x7f<>:"\\|?*]/_/g' <<< "$name")"
    name="$(sed -E 's/_+/_/g; s/^[[:space:]._]+//; s/[[:space:]]+$//' <<< "$name")"
    [[ -n "$name" ]] || name="_"
    echo "$name"
}

# The shared FILE-table query used against every source database (tracked-
# channel archives and fetch-files.sh search-result dirs alike). Channel
# resolution differs by source and is layered on by the caller:
# - tracked-archive rows: real CHANNEL_ID, but the caller already knows the
#   channel name for free from the archive directory path.
# - search-result rows: FILE.CHANNEL_ID is the literal placeholder "SEARCH"
#   (confirmed empirically); the real channel id lives in the file's own
#   JSON at DATA.channels[0]. The caller resolves that id to a name via the
#   Issue A catalog cache (read-only, no API call).
#
# message_context.type: a true Slack Canvas (mimetype
# application/vnd.slack-docs) with no MESSAGE_ID is 'channel_canvas';
# anything with a MESSAGE_ID is 'message_attachment' (ts resolved via a
# LEFT JOIN on MESSAGE, which is empty in search-result dbs so this is a
# no-op there); anything else (a non-canvas file found only via search, with
# no message linkage available) is 'search_result'.
read -r -d '' FILE_INDEX_SQL <<'SQL' || true
SELECT
    f.ID AS id,
    CASE
        WHEN f.CHANNEL_ID = 'SEARCH'
            THEN COALESCE(json_extract(f.DATA, '$.channels[0]'), '')
        ELSE f.CHANNEL_ID
    END AS channel_id,
    COALESCE(f.FILENAME, json_extract(f.DATA, '$.name')) AS filename,
    json_extract(f.DATA, '$.title') AS title,
    json_extract(f.DATA, '$.mimetype') AS mimetype,
    json_extract(f.DATA, '$.filetype') AS filetype,
    f.SIZE AS size,
    json_extract(f.DATA, '$.created') AS created,
    json_extract(f.DATA, '$.permalink') AS permalink,
    CASE
        WHEN json_extract(f.DATA, '$.mimetype') = 'application/vnd.slack-docs' AND f.MESSAGE_ID IS NULL
            THEN 'channel_canvas'
        WHEN f.MESSAGE_ID IS NOT NULL
            THEN 'message_attachment'
        ELSE 'search_result'
    END AS context_type,
    MAX(m.TS) AS context_ts,
    MIN(f.LOAD_DTTM) AS first_seen,
    MAX(f.LOAD_DTTM) AS last_seen
FROM FILE f
LEFT JOIN MESSAGE m ON f.MESSAGE_ID = m.ID
WHERE json_extract(f.DATA, '$.mimetype') NOT LIKE 'image/%'
GROUP BY f.ID
SQL

# query_file_index_db <db-path> -> JSON array per FILE_INDEX_SQL, [] if the
# db has no rows / doesn't exist.
query_file_index_db() {
    local db_path="$1"
    [[ -f "$db_path" ]] || { echo "[]"; return 0; }
    sqlite3 -json "$db_path" "$FILE_INDEX_SQL" 2>/dev/null || echo "[]"
}

# file_index_merge <existing-index-json> <new-entries-json> -> merged JSON
# array, deduped by id. Pure function (no I/O) so it's unit-testable without
# sqlite fixtures. On a collision, keeps the first-seen entry's descriptive
# fields (workspace/channel/filename/etc. and local_path) and recomputes
# first_seen/last_seen as the min/max across every occurrence -- entries
# earlier in <new-entries-json> win ties, so callers should append
# tracked-archive entries before search-result entries when a tracked
# archive is the more authoritative/reliable source for the same file.
file_index_merge() {
    local existing_json="$1" new_json="$2"
    jq -c -n --argjson existing "$existing_json" --argjson new "$new_json" '
        ($existing + $new) as $all
        | ($all | group_by(.id) | map(
            (.[0]) as $first
            | $first
            + { first_seen: (map(.first_seen) | min),
                last_seen: (map(.last_seen) | max) }
          ))
        | sort_by(.id)
    '
}
