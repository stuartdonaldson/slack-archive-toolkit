#!/usr/bin/env bash
# Nightly trigger: backup every tracked channel, then regenerate the f3*
# digest. Invoked by a Windows Scheduled Task running
# `wsl.exe -d Ubuntu -- /home/stuar/proj/SlackArchiver/scripts/nightly-backup-digest.sh`
# at 2am - see README.md "Getting Started" for the manual equivalent.
#
# Deliberately does not `set -e`: a partial backup failure (e.g. an
# expired workspace session, or a channel with an empty archive - see
# SlackBackup-8ew) must not prevent the digest step from running against
# whatever data IS available.
REPO_ROOT="/home/stuar/proj/SlackArchiver"
ARCHIVE_ROOT="$HOME/slack-backups"
LOG_FILE="$HOME/slack-backups/nightly.log"

# Task Scheduler -> wsl.exe runs this non-interactively, so ~/.bashrc/.profile
# are never sourced and PATH is minimal - slackdump (installed to ~/bin by
# scripts/install-slackdump.sh) and uv (installed to ~/.local/bin, used below
# to run ./slackbackup in this project's own venv) wouldn't otherwise be found.
export PATH="$HOME/bin:$HOME/.local/bin:$PATH"

# Defense-in-depth on top of backup_logic._log()'s explicit flush=True:
# Python fully block-buffers stdout once it's not a tty (i.e. redirected
# into this log file), so anything that prints without an explicit flush
# would otherwise sit invisible in the buffer for minutes during a long run.
export PYTHONUNBUFFERED=1

mkdir -p "$ARCHIVE_ROOT"
mkdir -p "$HOME/slack-exports"

# Canonical LLM context pack (docs/llm-context/, sat-ejk migration, decision
# recorded in docs/adr/0008-llm-context-pack-decomposition.md) is the active
# upload/copy source. The individually uploadable Project-knowledge files
# live under uploads/; refresh a curated ~/slack-exports/llm-context/ runtime
# subtree each run so operator uploads stay in sync with git. Mirror the
# whole tree EXCEPT planning/review/maintenance material that must not reach
# the runtime upload area — a deny-list via rsync --exclude, not a per-file
# allow-list, so a new prompt or supplemental file is picked up automatically
# without editing this script.
mkdir -p "$HOME/slack-exports/llm-context"
rsync -a --delete \
   --exclude 'README.md' \
   --exclude 'MIGRATION-PLAN.md' \
   --exclude 'REVIEW-*.md' \
   --exclude 'VALIDATION-RESULTS.md' \
   --exclude 'validation-set.md' \
    --exclude 'uploads/supplemental/archive/' \
    --exclude 'uploads/supplemental/sources/' \
   "$REPO_ROOT/docs/llm-context/" "$HOME/slack-exports/llm-context/"
# Excluded: this dir's own operator-facing README (assembly/maintenance
# guide, not upload content), planning/review/validation records, archived
# superseded supplemental snapshots, and raw source material backing a
# cumulative supplemental file (e.g. sotn-summaries.md's transcripts) — citation
# backup, not upload material. The supplemental index is retained under
# uploads/ because it is individually uploaded with selected supplemental files.

# The legacy per-file prompt/context docs (F3 culture notes, ingestion/
# newsletter/FNG/report-query prompts) were retired in sat-ejk.5 once the
# canonical pack above was validated and integrated — no longer copied here.

{
    echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) nightly backup+digest starting ====="
    cd "$REPO_ROOT" || exit 1

    # Keep slackdump credentials in sync with Slack's cookie rotation before the
    # backup (bd SlackBackup-5df): headless re-capture from the persistent browser
    # profile so sessions don't silently expire between nightly runs. Non-fatal -
    # a hard logout still needs an interactive `npm run refresh`.
    "$REPO_ROOT/scripts/auth-refresh/keepalive.sh" || echo "----- keepalive exited $? (continuing) -----"

    # Announce any still-expired workspaces up front (bd SlackBackup-d70) rather
    # than discovering them channel-by-channel mid-run. Informational only -
    # always exits 0, so it never blocks the backup below.
    "$REPO_ROOT/scripts/preflight-auth.sh" channels.json

    # Pick up newly-created public channels (e.g. "disc-it" was missed for
    # weeks before someone noticed and registered it by hand) before backing
    # up, so a channel created since last night's run gets archived in
    # *this* run instead of waiting for someone to catch it manually.
    # channel_logic.register_matching() was built for exactly this ("run
    # nightly" is in its own docstring); it already only *registers*
    # channels.json-missing ones, skipping private/archived/"shuttered*"/
    # already-registered regardless of glob - nothing to optimize there.
    # The cost is the FULL (non-member-only) catalog listing register_matching
    # does per workspace to even know what's out there to diff against -
    # docs/references/slackdump-cli-notes.md warns this can run several
    # minutes and be rate-limit-prone per workspace, and originally motivated
    # rotating one workspace's scan per night (day-of-year mod workspace
    # count) instead of scanning all of them. Measured in practice (2026-08-07
    # f3tundra, 2026-08-08 f3cascades) it's actually ~1.5-2 minutes per
    # workspace, not "several" - cheap enough across all 9 registered
    # workspaces that scanning every one nightly (via the 'f3*'/'*'-equivalent
    # workspace glob register_matching already supports) is worth the ~15-20
    # min it adds, so newly-created channels show up the very next run instead
    # of waiting up to a week for their rotation slot.
    echo "channel register: scanning all registered workspaces tonight"
    ./slackbackup channel register '*' '*' --channels-file channels.json 2>&1 | grep -v ' — already-registered$'
    echo "----- channel register exited ${PIPESTATUS[0]} -----"

    ./slackbackup backup run channels.json "$ARCHIVE_ROOT"
    echo "----- backup run exited $? -----"

    # Per-recipient report jobs (jobs/*.json, gitignored - see .gitignore's
    # comment on that pattern): each job file names its own workspace
    # subset, channels file, and output path. The glob is quoted so the
    # shell passes it through literally - --jobs does its own comma+glob
    # expansion (selector_logic.expand_path_selector), same paradigm as
    # --workspace/--channel selectors elsewhere in this CLI.
    ./slackbackup export digest --archive-root "$ARCHIVE_ROOT" --jobs "$REPO_ROOT/jobs/*.json"
    echo "----- job digests exited $? -----"

    echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) nightly backup+digest finished ====="
} >> "$LOG_FILE" 2>&1
