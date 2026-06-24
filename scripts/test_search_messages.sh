#!/usr/bin/env bash
# Unit tests for scripts/lib/message_search_helpers.sh — pure logic only,
# no live slackdump/API calls. A manual/live smoke test is described at the
# bottom; it is NOT run by this script.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/message_search_helpers.sh"

FAILED=0

assert_contains() {
    local name="$1" haystack="$2" needle="$3"
    if grep -qF -- "$needle" <<< "$haystack"; then
        echo "PASS: $name"
    else
        echo "FAIL: $name — expected to find: $needle" >&2
        FAILED=1
    fi
}

assert_not_contains() {
    local name="$1" haystack="$2" needle="$3"
    if grep -qF -- "$needle" <<< "$haystack"; then
        echo "FAIL: $name — did not expect to find: $needle" >&2
        FAILED=1
    else
        echo "PASS: $name"
    fi
}

# Real `TXT` column content: Slack pre-escapes bare "&" to "&amp;", but
# leaves its own <@U..|name> mention syntax as literal, unescaped angle
# brackets (that's syntax, not literal text) - confirmed empirically.
RESULTS='[
  {"workspace":"f3tundra","channel_id":"C1","channel_name":"general","ts":"1700000000.000000","txt":"older message","permalink":"https://x/p1"},
  {"workspace":"f3kirkland","channel_id":"C2","channel_name":"chat","ts":"1800000000.000000","txt":"newer &amp; stuff <@U123|name>","permalink":"https://x/p2"}
]'

HTML="$(render_messages_html "$RESULTS" "test query")"

assert_contains "html: includes the query in the title" "$HTML" "Slack search: test query"
assert_contains "html: result count rendered" "$HTML" "2 result(s)"
assert_contains "html: channel link built from workspace + channel id" "$HTML" 'href="https://f3kirkland.slack.com/archives/C2"'
assert_contains "html: permalink rendered" "$HTML" 'href="https://x/p2"'
assert_contains "html: pre-escaped Slack ampersand renders once, not double-escaped" "$HTML" "newer &amp; stuff"
assert_not_contains "html: pre-escaped ampersand is not double-escaped to &amp;amp;" "$HTML" "&amp;amp;"
assert_contains "html: Slack's raw <@..> mention syntax is escaped, not left as a literal tag" "$HTML" "&lt;@U123|name&gt;"
assert_not_contains "html: raw unescaped mention syntax does not leak through as a bogus tag" "$HTML" "<@U123|name>"

# most-recent-first ordering: the newer message's permalink should appear
# before the older message's permalink in the rendered output.
NEWER_POS="$(grep -n 'href="https://x/p2"' <<< "$HTML" | head -1 | cut -d: -f1)"
OLDER_POS="$(grep -n 'href="https://x/p1"' <<< "$HTML" | head -1 | cut -d: -f1)"
if [[ "$NEWER_POS" -lt "$OLDER_POS" ]]; then
    echo "PASS: html: most-recent message rendered before older one"
else
    echo "FAIL: html: expected newer message (line $NEWER_POS) before older (line $OLDER_POS)" >&2
    FAILED=1
fi

EMPTY_HTML="$(render_messages_html "[]" "no matches query")"
assert_contains "html: empty result set renders a 'No results' message" "$EMPTY_HTML" "No results"
assert_contains "html: empty result set still shows 0 result(s)" "$EMPTY_HTML" "0 result(s)"

# channel_name missing/null falls back to the raw channel id
FALLBACK_RESULTS='[{"workspace":"f3tundra","channel_id":"C3","channel_name":null,"ts":"1700000000.000000","txt":"x","permalink":"https://x/p3"}]'
FALLBACK_HTML="$(render_messages_html "$FALLBACK_RESULTS" "fallback test")"
assert_contains "html: missing channel_name falls back to raw channel id" "$FALLBACK_HTML" ">#C3<"

exit "$FAILED"

# --- Manual/live smoke test (not run by this script) ---
# To verify against the real Slack API once:
#   scripts/search-messages.sh --out /tmp/smoke.html convergence
# should: skip any unregistered f3* workspace with a warning, search every
# registered one, and write an HTML file with results sorted most-recent
# first, each linking to its channel and to the message itself in Slack.
