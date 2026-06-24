#!/usr/bin/env bash
# build-file-index - unify non-image files/canvases from tracked-channel
# archives and fetch-files.sh's search-result databases into one
# deduplicated index.json, with the actual file blobs copied into one
# browsable tree. Read-only with respect to both source archives; never
# calls the Slack API itself.
#
# Usage:
#   build-file-index.sh <out-files-dir> <index.json> \
#                        --archive-root <path> --search-root <path>
#   build-file-index.sh --help
#
#   Input  : <archive-root>/<ws>/<channel>/slackdump.sqlite   (from backup.sh)
#            <search-root>/<ws>/<term>/slackdump.sqlite       (from fetch-files.sh)
#   Output : <out-files-dir>/<ws>/<channel>/<filename>__<file-id>.<ext>
#            <index.json> (one array, one entry per unique file id)
#
# Non-image filtering is `mimetype NOT LIKE 'image/%'` against each FILE
# row's DATA blob (slackdump stores the raw Slack file JSON there; there is
# no separate MIMETYPE column - see docs/references/slackdump-cli-notes.md).
# This covers canvases for free: a Canvas is just a FILE row with mimetype
# application/vnd.slack-docs.
#
# Tracked-archive rows carry a real CHANNEL_ID, but the channel name is
# already known for free from the archive directory path, so it's used
# directly. Search-result rows carry the literal placeholder CHANNEL_ID
# "SEARCH" (confirmed empirically) - the real channel id lives in the
# file's own JSON at DATA.channels[0], and is resolved to a name via the
# channel catalog cache (lib/channel_catalog.sh) - never a fresh
# `slackdump list channels` call, per that script's binding constraint.
#
# Idempotent re-run: a file id already in <index.json> is not re-copied;
# stdout follows export_transform.sh's wrote/skipped/empty convention.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/channel_catalog.sh"
source "$SCRIPT_DIR/lib/file_index_helpers.sh"

usage() {
    cat >&2 <<'EOF'
usage: build-file-index.sh <out-files-dir> <index.json> \
                            --archive-root <path> --search-root <path>
EOF
    exit 64
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    usage
fi

OUT_FILES_DIR="${1:?}"
INDEX_JSON="${2:?}"
shift 2

ARCHIVE_ROOT="" SEARCH_ROOT=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --archive-root) ARCHIVE_ROOT="${2:?--archive-root needs a value}"; shift 2 ;;
        --search-root)  SEARCH_ROOT="${2:?--search-root needs a value}"; shift 2 ;;
        *) echo "build-file-index: unknown argument '$1'" >&2; usage ;;
    esac
done

[[ -n "$ARCHIVE_ROOT" && -n "$SEARCH_ROOT" ]] || usage

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT
NEW_ENTRIES_LINES="$WORKDIR/new-entries.jsonl"
: > "$NEW_ENTRIES_LINES"

EXISTING_INDEX="[]"
[[ -f "$INDEX_JSON" ]] && EXISTING_INDEX="$(cat "$INDEX_JSON")"
EXISTING_IDS="$(jq -r '.[].id' <<< "$EXISTING_INDEX")"

# --- tracked-channel archives: channel name known for free from the path ---
if [[ -d "$ARCHIVE_ROOT" ]]; then
    while IFS= read -r db_path; do
        rel="${db_path#"$ARCHIVE_ROOT"/}"
        ws="${rel%%/*}"
        channel="${rel#*/}"; channel="${channel%%/*}"

        query_file_index_db "$db_path" | jq -c --arg ws "$ws" --arg channel "$channel" \
            --arg root "$ARCHIVE_ROOT/$ws/$channel" \
            '.[] | . + {workspace: $ws, channel: $channel, source_root: $root}' \
            >> "$NEW_ENTRIES_LINES"
    done < <(find "$ARCHIVE_ROOT" -mindepth 3 -maxdepth 3 -type f -name slackdump.sqlite | sort)
fi

# --- search-result dirs: channel resolved via the catalog by real channel id ---
if [[ -d "$SEARCH_ROOT" ]]; then
    while IFS= read -r db_path; do
        rel="${db_path#"$SEARCH_ROOT"/}"
        ws="${rel%%/*}"
        source_root="${db_path%/slackdump.sqlite}"

        query_file_index_db "$db_path" | jq -c --arg ws "$ws" --arg root "$source_root" \
            '.[] | . + {workspace: $ws, source_root: $root}' \
        | while IFS= read -r entry; do
            cid="$(jq -r '.channel_id' <<< "$entry")"
            name="$(catalog_name_by_id "$ws" "$cid")"
            [[ -n "$name" ]] || name="$cid"
            jq -c --arg channel "$name" '. + {channel: $channel}' <<< "$entry"
        done >> "$NEW_ENTRIES_LINES"
    done < <(find "$SEARCH_ROOT" -mindepth 3 -maxdepth 3 -type f -name slackdump.sqlite | sort)
fi

NEW_ENTRIES="$(jq -c -s '.' "$NEW_ENTRIES_LINES")"
MERGED_INDEX="$(file_index_merge "$EXISTING_INDEX" "$NEW_ENTRIES")"

if [[ "$(jq 'length' <<< "$MERGED_INDEX")" -eq 0 ]]; then
    echo "empty (no non-image files found)"
    exit 0
fi

FINAL_ENTRIES_LINES="$WORKDIR/final-entries.jsonl"
: > "$FINAL_ENTRIES_LINES"

while IFS= read -r entry; do
    id="$(jq -r '.id' <<< "$entry")"
    if grep -qxF "$id" <<< "$EXISTING_IDS"; then
        echo "skipped (exists) $id"
        echo "$entry" >> "$FINAL_ENTRIES_LINES"
        continue
    fi

    workspace="$(jq -r '.workspace' <<< "$entry")"
    channel="$(jq -r '.channel' <<< "$entry")"
    filename="$(jq -r '.filename // ""' <<< "$entry")"
    source_root="$(jq -r '.source_root' <<< "$entry")"

    if [[ -z "$filename" ]]; then
        echo "empty (no filename) $id" >&2
        echo "$entry" >> "$FINAL_ENTRIES_LINES"
        continue
    fi

    src_blob="$source_root/__uploads/$id/$filename"
    if [[ ! -f "$src_blob" ]]; then
        echo "empty (blob not found) $id" >&2
        echo "$entry" >> "$FINAL_ENTRIES_LINES"
        continue
    fi

    safe_name="$(sanitize_filename "$filename")"
    base="${safe_name%.*}"
    ext="${safe_name##*.}"
    if [[ "$base" == "$safe_name" ]]; then
        dest_name="${safe_name}__${id}"
    else
        dest_name="${base}__${id}.${ext}"
    fi

    dest_dir="$OUT_FILES_DIR/$workspace/$channel"
    mkdir -p "$dest_dir"
    [[ -f "$dest_dir/$dest_name" ]] || cp "$src_blob" "$dest_dir/$dest_name"

    jq -c --arg local_path "$dest_dir/$dest_name" '. + {local_path: $local_path}' <<< "$entry" \
        >> "$FINAL_ENTRIES_LINES"
    echo "wrote $id ($workspace/$channel/$dest_name)"
done < <(jq -c '.[]' <<< "$MERGED_INDEX")

TMP_FILE="$(mktemp)"
jq -c -s '
    map({id, workspace, channel, filename, title, mimetype, filetype, size,
         created, message_context: {type: .context_type, ts: .context_ts},
         permalink, local_path, first_seen, last_seen})
' "$FINAL_ENTRIES_LINES" > "$TMP_FILE"
mv "$TMP_FILE" "$INDEX_JSON"
