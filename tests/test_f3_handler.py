"""Tests for the F3-specific leadership-inference handler (handlers/f3.py).
Moved out of test_export_digest_logic.py when that logic was extracted into
its own module - see handlers/__init__.py's docstring for the handler
protocol these functions implement, and test_export_digest_logic.py for the
general-purpose build_digest/build_user_profiles integration tests.
"""
from slackbackup.handlers import f3


def test_derive_leadership_none_for_plain_display_name():
    assert f3.derive_leadership("Al") is None
    assert f3.derive_leadership(None) is None
    assert f3.derive_leadership("") is None


def test_derive_leadership_matches_title_and_region():
    signal = f3.derive_leadership("Columbia - Cascades Region Nantan")
    assert signal["possible_f3_name"] == "Columbia"
    assert signal["possible_region"] == "F3 Cascades"
    assert signal["possible_roles"] == [
        {
            "position": "Nantan", "basis": "display_name", "confidence": "medium_high",
            "needs_confirmation": True, "status": "unclear", "is_current": None,
            "modifier_detected": None, "source_text": "Columbia - Cascades Region Nantan",
        }
    ]


def test_derive_leadership_no_separator_is_lower_confidence_no_region():
    signal = f3.derive_leadership("Comz Guy")
    assert signal["possible_f3_name"] == "Comz Guy"
    assert signal["possible_region"] is None
    assert signal["possible_roles"][0]["confidence"] == "medium"


def test_derive_leadership_compact_hyphen_region_parses_name_correctly():
    # Reported broken in docs/llm-leadership-improvement.md: no spaces
    # around the hyphen, so the old separator-only logic fell back to the
    # whole string as the "name".
    signal = f3.derive_leadership("Montoya-Kirkland Region Nantan")
    assert signal["possible_f3_name"] == "Montoya"
    assert signal["possible_region"] == "F3 Kirkland"
    assert signal["possible_roles"][0]["confidence"] == "medium_high"


def test_derive_leadership_paren_region_form():
    signal = f3.derive_leadership("Quesadillah (F3 Ellensburg Nantan)")
    assert signal["possible_f3_name"] == "Quesadillah"
    # Ellensburg isn't a tracked f3* region - correctly left unresolved
    # rather than guessed.
    assert signal["possible_region"] is None
    assert signal["possible_roles"][0]["confidence"] == "medium_high"


def test_derive_leadership_name_then_role_then_region_order():
    signal = f3.derive_leadership("Tardy - Kirkland 3rd F")
    assert signal["possible_f3_name"] == "Tardy"
    assert signal["possible_region"] == "F3 Kirkland"
    assert {r["position"] for r in signal["possible_roles"]} == {"3rd F"}


def test_derive_leadership_weaselshaker_no_space_variant():
    signal = f3.derive_leadership("Voltaire - Weaselshaker Tundra")
    assert signal["possible_f3_name"] == "Voltaire"
    assert signal["possible_region"] == "F3 Tundra"
    assert {r["position"] for r in signal["possible_roles"]} == {"Weasel Shaker"}


def test_derive_leadership_multiple_roles_no_redundant_bare_q():
    signal = f3.derive_leadership("Columbia - 1stF Q Cascades")
    assert signal["possible_f3_name"] == "Columbia"
    assert signal["possible_region"] == "F3 Cascades"
    assert {r["position"] for r in signal["possible_roles"]} == {"1st F", "Q"}


def test_derive_leadership_specific_q_variant_suppresses_bare_q():
    signal = f3.derive_leadership("Sitwell - Site Q Kirkland")
    positions = {r["position"] for r in signal["possible_roles"]}
    assert positions == {"Site Q"}
    assert "Q" not in positions


def test_derive_leadership_title_two_segments_different_regions():
    # "Redmond Ridge Site Q, Redmond Comz Q" — real title format per user feedback.
    signal = f3.derive_leadership("Combine", title="Redmond Ridge Site Q, Redmond Comz Q")
    assert signal["possible_f3_name"] == "Combine"
    roles = signal["possible_roles"]
    site_q = next(r for r in roles if r["position"] == "Site Q")
    comz = next(r for r in roles if r["position"] == "Comz")
    # Site Q is AO-scoped: emits possible_ao for the workout location and
    # possible_region derived from known region names within the prefix.
    assert site_q["basis"] == "title"
    assert site_q["confidence"] == "high"
    assert site_q["needs_confirmation"] is False
    assert site_q["possible_ao"] == "Redmond Ridge"
    assert site_q["possible_region"] == "F3 Redmond"
    # Comz Q is region-scoped: possible_region only, no possible_ao.
    assert comz["basis"] == "title"
    assert comz["possible_region"] == "F3 Redmond"
    assert "possible_ao" not in comz


def test_derive_leadership_title_only_no_display_name_match():
    # Title alone (plain display name) should still surface roles.
    signal = f3.derive_leadership("Dude", title="Kirkland Nantan")
    assert signal is not None
    positions = {r["position"] for r in signal["possible_roles"]}
    assert "Nantan" in positions
    title_roles = [r for r in signal["possible_roles"] if r["basis"] == "title"]
    assert all(r["confidence"] == "high" for r in title_roles)
    assert all(r["needs_confirmation"] is False for r in title_roles)


def test_derive_leadership_none_when_both_sources_empty():
    assert f3.derive_leadership("Dude", title="Community Manager") is None
    assert f3.derive_leadership(None, title=None) is None


# --- modifier / tenure tests ---


def test_derive_leadership_modifier_emeritus_after_role():
    # Real sanitized example: "Seattle Region Nantan Emeritus - 206.555.1234"
    # The modifier appears after the role keyword; trailing content is noise.
    signal = f3.derive_leadership("Padre - Seattle Region Nantan Emeritus - 206.555.1234")
    assert signal is not None
    role = next(r for r in signal["possible_roles"] if r["position"] == "Nantan")
    assert role["status"] == "emeritus"
    assert role["is_current"] is False
    assert role["modifier_detected"].lower() == "emeritus"


def test_derive_leadership_modifier_former_before_role():
    signal = f3.derive_leadership("Former Nantan")
    assert signal is not None
    role = signal["possible_roles"][0]
    assert role["status"] == "former"
    assert role["is_current"] is False
    assert "former" in role["modifier_detected"].lower()


def test_derive_leadership_modifier_retired():
    signal = f3.derive_leadership("Retired Weasel Shaker")
    assert signal is not None
    role = signal["possible_roles"][0]
    assert role["status"] == "retired"
    assert role["is_current"] is False


def test_derive_leadership_modifier_ex_prefix():
    signal = f3.derive_leadership("Ex-Nantan")
    assert signal is not None
    role = signal["possible_roles"][0]
    assert role["status"] == "former"
    assert role["is_current"] is False


def test_derive_leadership_no_modifier_display_name_is_unclear():
    # No separator → confidence=medium → status="unclear", is_current=None
    signal = f3.derive_leadership("Nantan")
    assert signal is not None
    role = signal["possible_roles"][0]
    assert role["status"] == "unclear"
    assert role["is_current"] is None
    assert role["modifier_detected"] is None


def test_derive_leadership_title_no_modifier_is_current():
    # Title field with no modifier and confidence="high" → status="current"
    signal = f3.derive_leadership("Dude", title="Kirkland Nantan")
    title_roles = [r for r in signal["possible_roles"] if r["basis"] == "title"]
    assert title_roles
    assert all(r["status"] == "current" for r in title_roles)
    assert all(r["is_current"] is True for r in title_roles)
    assert all(r["modifier_detected"] is None for r in title_roles)


def test_derive_leadership_title_modifier_scoped_to_segment():
    # "Former Nantan, Kirkland Comz Q" — modifier only in the first segment;
    # second segment has no modifier and should be "current".
    signal = f3.derive_leadership("Dude", title="Former Cascades Nantan, Kirkland Comz Q")
    nantan = next(r for r in signal["possible_roles"] if r["position"] == "Nantan")
    comz = next(r for r in signal["possible_roles"] if r["position"] == "Comz")
    assert nantan["status"] == "former"
    assert nantan["is_current"] is False
    assert comz["status"] == "current"
    assert comz["is_current"] is True


def test_derive_leadership_source_text_captured():
    signal = f3.derive_leadership("Columbia - Cascades Region Nantan")
    role = signal["possible_roles"][0]
    assert role["source_text"] == "Columbia - Cascades Region Nantan"


def test_derive_leadership_title_source_text_is_segment():
    signal = f3.derive_leadership("Dude", title="Redmond Ridge Site Q, Redmond Comz Q")
    site_q = next(r for r in signal["possible_roles"] if r["position"] == "Site Q")
    comz = next(r for r in signal["possible_roles"] if r["position"] == "Comz")
    assert site_q["source_text"] == "Redmond Ridge Site Q"
    assert comz["source_text"] == "Redmond Comz Q"


