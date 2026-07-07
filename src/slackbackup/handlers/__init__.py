"""Region/workspace-specific digest processing, pulled out of export_logic.py
so the export engine stays general-purpose. A handler module implements two
functions:

    annotate_profile(display_name, title) -> dict | None
        Per-profile tagging, called once per user in build_user_profiles().
        The result is stashed on the profile as "derived_leadership".

    build_leadership(profiles_doc) -> dict
        Aggregates the already-tagged profiles_doc (see above) into the
        digest's top-level "leadership" section: {profile_role_matches,
        by_region, former_by_region}. Called once per build_digest().

Add a new handler by dropping a module in this package (following f3.py's
shape) and registering it in _HANDLERS below.
"""
from __future__ import annotations

from . import f3

_HANDLERS = {"f3": f3}
NAMES = sorted(_HANDLERS)


def get(name: str | None):
    """None means "no handler" (skip tagging/leadership entirely) -
    the caller's own default, not this function's - job files and CLI
    flags both use None to mean "not configured"."""
    if name is None:
        return None
    try:
        return _HANDLERS[name]
    except KeyError:
        raise ValueError(f"unknown handler {name!r} (known: {sorted(_HANDLERS)})") from None
