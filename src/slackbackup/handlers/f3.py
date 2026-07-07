"""F3 (a men's fitness/leadership organization, workspaces named f3<region>)
leadership inference: best-effort, display-name/profile-title signal per
docs/llm-export-suggestion.md's "profile-inferred roles" proposal, tuned per
docs/llm-leadership-improvement.md's feedback (dedup, wider role coverage,
compact-name-region parsing). Extend the two data lists freely - they're
config, not logic; the patterns list needs a regex if a new title doesn't
fit \\bword\\b matching, but most will.

Registered as handler "f3" in handlers/__init__.py - opt in per job via
jobs/*.json's "leadership_handler" field, or via export.py's
--leadership-handler flag for the plain (non-job) `export digest` command.
Applying this to a non-F3 workspace (e.g. a personal/other-org Slack) would
just produce noise - these patterns assume F3's own role vocabulary.
"""
from __future__ import annotations

import re

_LEADERSHIP_TITLE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("Nantan", re.compile(r"nantan", re.I)),
    ("Weasel Shaker", re.compile(r"weasel\s*shaker", re.I)),
    ("1st F", re.compile(r"\b1st\s*f\b|\bfirst\s*f\b", re.I)),
    ("2nd F", re.compile(r"\b2nd\s*f\b|\bsecond\s*f\b", re.I)),
    ("3rd F", re.compile(r"\b3rd\s*f\b|\bthird\s*f\b", re.I)),
    ("Comz", re.compile(r"\bcomz\b|\bcommunications?\b", re.I)),
    ("Site Q", re.compile(r"\bsite[-\s]?q\b", re.I)),
    ("Region Q", re.compile(r"\bregion\s*q\b", re.I)),
    ("AOQ", re.compile(r"\baoq\b|\bao[-\s]q\b", re.I)),
    ("Q Lead", re.compile(r"\bq\s*lead\b", re.I)),
    ("SLT", re.compile(r"\bslt\b|\bshared\s+leadership\s+team\b", re.I)),
    ("OIC", re.compile(r"\boic\b", re.I)),
    ("EH Lead", re.compile(r"\beh\s*lead\b", re.I)),
    ("Fight Lead", re.compile(r"\bfight\s*lead\b", re.I)),
    ("FNG Lead", re.compile(r"\bfng\s*lead\b", re.I)),
    # Bare "Q" last and lowest-confidence signal of the bunch - dropped
    # below when a more specific Q-variant above already matched, so a
    # single mention doesn't produce two redundant role entries.
    ("Q", re.compile(r"\bq\b", re.I)),
]

_SPECIFIC_Q_TITLES = {"Q Lead", "Site Q", "Region Q", "AOQ"}

# Roles scoped to a specific AO/channel rather than the whole region.
# "Redmond Ridge Site Q" → Site Q for the ao-redmond-ridge channel.
_AO_SCOPED_ROLES = {"Site Q", "AOQ", "OIC"}

# Ordered by specificity — emeritus/retired before the generic "former" bucket.
# "\bex-" (no closing \b) intentionally matches "ex-" as a prefix modifier
# (e.g. "Ex-Nantan") without requiring a word boundary after the hyphen.
_MODIFIER_TO_STATUS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bemeritus\b", re.I), "emeritus"),
    (re.compile(r"\bretired\b", re.I), "retired"),
    (re.compile(
        r"\bformer\b|\bex-|\bpast\b|\bprevious\b|\boutgoing\b"
        r"|\bstepping\s+down\b|\bwas\b|\bused\s+to\s+be\b",
        re.I,
    ), "former"),
]


def _detect_modifier(text: str) -> tuple[str | None, str | None]:
    """Returns (matched_text, status) for the first tenure modifier found in
    `text`, or (None, None) if none present. Checks emeritus/retired before
    the generic "former" bucket so they keep their own label."""
    for pattern, status in _MODIFIER_TO_STATUS:
        m = pattern.search(text)
        if m:
            return m.group(0), status
    return None, None


def _role_status(modifier_status: str | None, confidence: str) -> tuple[str, bool | None]:
    """Derive (status, is_current) from modifier presence and confidence.
    Modifier always wins: is_current=False, status from the modifier.
    No modifier: confidence="high" → "current"/True; lower → "unclear"/None
    (display-name sources are not maintained so we can't assert is_current)."""
    if modifier_status is not None:
        return modifier_status, False
    if confidence == "high":
        return "current", True
    return "unclear", None

_REGION_NAMES = {
    "f3pugetsound": "Puget Sound",
    "f3kirkland": "Kirkland",
    "f3cascades": "Cascades",
    "f3tundra": "Tundra",
    "f3redmond": "Redmond",
    "f3seattle": "Seattle",
}

_NAME_SEPARATORS = (" - ", " – ", " — ", "|")
_PAREN_RE = re.compile(r"\s*\(")
_COMPACT_HYPHEN_REGION_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9_]+)-(?:" + "|".join(re.escape(r) for r in _REGION_NAMES.values()) + r")\b",
    re.I,
)


def _match_titles(display_name: str) -> list[str]:
    matched = [
        canonical
        for canonical, pattern in _LEADERSHIP_TITLE_PATTERNS
        if pattern.search(display_name)
    ]
    if "Q" in matched and any(title in matched for title in _SPECIFIC_Q_TITLES):
        matched.remove("Q")
    return matched


def _split_possible_name(display_name: str) -> tuple[str, bool]:
    """Returns (possible_f3_name, structured) - structured is True when a
    recognized name/region delimiter was found, used to set confidence.
    Handles "<Name> - <Region> Region <Role>", "<Name> (<Region> <Role>)",
    and the compact "<Name>-<Region> Region <Role>" form (no spaces around
    the hyphen) - reported broken for "Montoya-Kirkland Region Nantan"."""
    for sep in _NAME_SEPARATORS:
        if sep in display_name:
            return display_name.split(sep, 1)[0].strip(), True

    paren_match = _PAREN_RE.search(display_name)
    if paren_match:
        return display_name[: paren_match.start()].strip(), True

    compact_match = _COMPACT_HYPHEN_REGION_RE.match(display_name)
    if compact_match:
        return compact_match.group("name"), True

    return display_name.strip(), False


def _title_segment_prefix(segment: str, position: str) -> str | None:
    """Text before the role keyword in a title segment — the location part
    of '<Location> <Role>', e.g. 'Redmond Ridge' from 'Redmond Ridge Site Q'."""
    _, pattern = next(((p, r) for p, r in _LEADERSHIP_TITLE_PATTERNS if p == position), (None, None))
    if pattern is None:
        return None
    m = pattern.search(segment)
    return segment[: m.start()].strip() or None if m else None


def _parse_title_segments(title: str) -> list[dict]:
    """Parse a Slack profile title field into per-segment role entries.
    Each comma-separated segment is treated as '<Location> <Role>', e.g.
    'Redmond Ridge Site Q, Redmond Comz Q'. Title is explicitly set so
    these roles carry higher confidence than display-name inference.

    AO-scoped roles (Site Q, AOQ, OIC) emit possible_ao (the AO/channel
    name, e.g. 'Redmond Ridge') alongside possible_region. Regional roles
    emit only possible_region.

    Modifier words (Emeritus, Former, Retired, etc.) detected per segment
    set status/is_current so former roles don't pollute the current
    leadership summary."""
    roles = []
    for segment in re.split(r"\s*,\s*", title):
        segment = segment.strip()
        if not segment:
            continue
        matched = _match_titles(segment)
        if not matched:
            continue
        matched_region = next(
            (region for region in _REGION_NAMES.values() if region.lower() in segment.lower()),
            None,
        )
        modifier_detected, modifier_status = _detect_modifier(segment)
        status, is_current = _role_status(modifier_status, "high")
        for position in matched:
            entry: dict = {
                "position": position,
                "basis": "title",
                "confidence": "high",
                "needs_confirmation": False,
                "possible_region": f"F3 {matched_region}" if matched_region else None,
                "status": status,
                "is_current": is_current,
                "modifier_detected": modifier_detected,
                "source_text": segment,
            }
            if position in _AO_SCOPED_ROLES:
                entry["possible_ao"] = _title_segment_prefix(segment, position)
            roles.append(entry)
    return roles


def derive_leadership(display_name: str | None, title: str | None = None) -> dict | None:
    """Display names and profile titles are both practical working signals
    for "who currently holds this role". Display-name inference is
    best-effort (needs_confirmation=True); title-field roles carry higher
    confidence since the field is set explicitly. Returns None when neither
    source matches any known F3 role pattern."""
    dn_roles: list[dict] = []
    dn_region: str | None = None
    possible_f3_name: str | None = None

    if display_name:
        matched_titles = _match_titles(display_name)
        possible_f3_name, structured = _split_possible_name(display_name)
        if matched_titles:
            confidence = "medium_high" if structured else "medium"
            dn_region = next(
                (region for region in _REGION_NAMES.values() if region.lower() in display_name.lower()),
                None,
            )
            modifier_detected, modifier_status = _detect_modifier(display_name)
            status, is_current = _role_status(modifier_status, confidence)
            dn_roles = [
                {
                    "position": t,
                    "basis": "display_name",
                    "confidence": confidence,
                    "needs_confirmation": True,
                    "status": status,
                    "is_current": is_current,
                    "modifier_detected": modifier_detected,
                    "source_text": display_name,
                }
                for t in matched_titles
            ]

    title_roles = _parse_title_segments(title) if title else []

    if not dn_roles and not title_roles:
        return None

    return {
        "possible_f3_name": possible_f3_name,
        "possible_region": f"F3 {dn_region}" if dn_region else None,
        "possible_roles": dn_roles + title_roles,
    }


# Handler protocol entry point (see handlers/__init__.py's docstring) -
# same function, named per the protocol so build_user_profiles() can call
# any handler uniformly.
annotate_profile = derive_leadership


_CONFIDENCE_RANK = {"medium": 1, "medium_high": 2, "high": 3}


def _build_leadership_by_region(raw_matches: list[dict]) -> tuple[list[dict], list[dict]]:
    """Dedupes raw_matches by (region, f3_name, position) - the same
    person commonly has a separate Slack account per workspace, each
    independently matching the same self-reported role; without this, the
    same leader is repeated once per workspace (reported in
    docs/llm-leadership-improvement.md).

    Returns (by_region, former_by_region): roles where is_current is not
    False go to by_region (current/unclear); roles where is_current is False
    go to former_by_region. When the same (region, f3_name, position) key
    has both former and non-former sources (unusual but possible across
    workspace accounts), they land in separate groups."""
    current_groups: dict[tuple, dict] = {}
    former_groups: dict[tuple, dict] = {}

    for record in raw_matches:
        derived = record["derived"]
        if derived is None:
            # Admin/owner-only entries (no display-name title match) have
            # no role/region to group by - they still appear in
            # profile_role_matches, just not in this rollup.
            continue
        f3_name = derived["possible_f3_name"]
        for role in derived["possible_roles"]:
            region = role.get("possible_region") or derived["possible_region"] or "Unknown"
            key = (region, f3_name, role["position"])
            target = former_groups if role.get("is_current") is False else current_groups
            group = target.setdefault(
                key,
                {
                    "workspaces": set(), "display_names": set(), "profile_ids": set(),
                    "confidence": role["confidence"], "statuses": set(),
                },
            )
            group["workspaces"].add(record["workspace"])
            group["display_names"].add(record["display_name"])
            group["profile_ids"].add(record["id"])
            group["statuses"].add(role.get("status", "unclear"))
            if _CONFIDENCE_RANK.get(role["confidence"], 0) > _CONFIDENCE_RANK.get(group["confidence"], 0):
                group["confidence"] = role["confidence"]

    def _groups_to_list(groups: dict, *, former: bool) -> list[dict]:
        by_region: dict[str, list[dict]] = {}
        # Most-specific-wins ordering for status label within a group.
        _STATUS_PRIORITY = ("emeritus", "retired", "former", "current", "unclear")
        for (region, f3_name, position), group in groups.items():
            statuses = group["statuses"]
            status = next((s for s in _STATUS_PRIORITY if s in statuses), "unclear")
            # Keep is_current consistent with the resolved status: former
            # groups are always False; a current group is only True when its
            # status actually resolves to "current" (title-derived), else
            # None ("unclear" - display-name sources can't assert currency).
            is_current = False if former else (True if status == "current" else None)
            by_region.setdefault(region, []).append(
                {
                    "position": position,
                    "f3_name": f3_name,
                    "status": status,
                    "is_current": is_current,
                    "confidence": group["confidence"],
                    "basis": "display_name",
                    "seen_in_workspaces": sorted(group["workspaces"]),
                    "source_display_names": sorted(group["display_names"]),
                    "source_profile_ids": sorted(group["profile_ids"]),
                    # Always True, deliberately not matching the literal example
                    # in docs/llm-leadership-improvement.md: the same self-
                    # reported display name repeated across a person's per-
                    # workspace accounts is not independent corroboration, so it
                    # doesn't earn "confirmed" - basis is still display_name-only.
                    "needs_confirmation": True,
                }
            )
        return [
            {"region": r, "roles": sorted(by_region[r], key=lambda x: (x["position"], x["f3_name"] or ""))}
            for r in sorted(by_region)
        ]

    return (
        _groups_to_list(current_groups, former=False),
        _groups_to_list(former_groups, former=True),
    )


def build_leadership(profiles_doc: dict) -> dict:
    """Handler protocol entry point (see handlers/__init__.py's docstring).
    Scans profiles_doc's already-tagged profiles (via annotate_profile,
    stashed under "derived_leadership" by build_user_profiles) plus each
    profile's authoritative Slack workspace role, into the digest's
    top-level "leadership" section.

    Admin/owner/primary_owner is an authoritative Slack-platform role, not
    an inferred one - include the profile even when its display name
    doesn't match any F3 title pattern, so a workspace admin/owner is never
    silently dropped from the leadership list just because annotate_profile
    found nothing."""
    leadership: list[dict] = []
    for ws_entry in profiles_doc["workspaces"]:
        if ws_entry["status"] != "ok":
            continue
        for profile in ws_entry["profiles"]:
            signal = profile.get("derived_leadership")
            has_workspace_role = bool({"admin", "owner", "primary_owner"} & set(profile["slack_roles"]))
            if signal is None and not has_workspace_role:
                continue
            leadership.append(
                {
                    "id": profile["id"],
                    "workspace": ws_entry["workspace"],
                    "display_name": profile["display_name"],
                    "real_name": profile["real_name"],
                    "title": profile.get("title"),
                    "slack_roles": profile["slack_roles"],
                    "derived": signal,
                }
            )

    by_region, former_by_region = _build_leadership_by_region(leadership)
    return {
        "profile_role_matches": leadership,
        "by_region": by_region,
        "former_by_region": former_by_region,
    }
