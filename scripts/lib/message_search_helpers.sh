# Sourced helper: pure-logic pieces of search-messages.sh, split out for
# unit testing without a live slackdump/API call.

# render_messages_html <results-json-array> <query-label> -> full HTML
# document, most-recent message first. Pure function: takes already-
# collected result rows ({workspace, channel_id, channel_name, ts, txt,
# permalink}), does no I/O.
render_messages_html() {
    local results_json="$1" query_label="$2"
    local body
    # .txt needs care: Slack's own message text already HTML-entity-escapes
    # bare &, but leaves its own <@U..|name>/<#C..>/<url|label> mention/link
    # syntax as literal, unescaped angle brackets (that's Slack mrkdwn
    # syntax, not HTML). Embedding that raw risks the browser treating it as
    # a bogus tag and silently dropping it. Fix: decode Slack's partial
    # entity-escaping back to raw text first, then apply our own @html
    # uniformly across the whole string - escaped exactly once, no raw
    # "<...>" reaching the browser. Mentions/links render as escaped literal
    # text (e.g. "&lt;@U123|name&gt;"), not resolved names - this is a
    # plain-text-safe rendering, not a full mrkdwn-to-HTML renderer.
    body="$(jq -r '
        sort_by(.ts | tonumber) | reverse
        | map(
            (.ts | tonumber | gmtime | strftime("%Y-%m-%d %H:%M UTC")) as $when
            | "<div class=\"msg\"><div class=\"meta\"><span class=\"when\">\($when)</span> "
            + "<a class=\"channel\" href=\"https://\(.workspace).slack.com/archives/\(.channel_id)\">#\(.channel_name // .channel_id | @html)</a> "
            + "<span class=\"ws\">(\(.workspace | @html))</span> "
            + "<a class=\"permalink\" href=\"\(.permalink | @html)\">view in Slack ↗</a></div>"
            + "<pre class=\"text\">\(.txt // "" | gsub("&lt;"; "<") | gsub("&gt;"; ">") | gsub("&amp;"; "&") | @html)</pre></div>"
          )
        | join("\n")
    ' <<< "$results_json")"

    local count
    count="$(jq 'length' <<< "$results_json")"
    if [[ "$count" -eq 0 ]]; then
        body='<p class="empty">No results.</p>'
    fi

    local escaped_label
    escaped_label="$(jq -Rr '@html' <<< "$query_label")"

    cat <<HTML
<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>Slack search: $escaped_label</title>
<style>
body { font-family: sans-serif; max-width: 800px; margin: 2em auto; padding: 0 1em; }
h1 { font-size: 1.2em; }
.msg { border-bottom: 1px solid #ddd; padding: 1em 0; }
.meta { color: #555; font-size: 0.9em; margin-bottom: 0.3em; }
.when { font-weight: bold; }
.ws { color: #888; }
.text { white-space: pre-wrap; font-family: inherit; margin: 0; }
a { color: #1264a3; text-decoration: none; }
a:hover { text-decoration: underline; }
.empty { color: #888; }
</style>
</head><body>
<h1>Slack search: $escaped_label</h1>
<p class="count">$count result(s), most recent first.</p>
$body
</body></html>
HTML
}
