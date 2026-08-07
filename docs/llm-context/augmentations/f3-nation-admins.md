# F3-Nation admins by region

| Field | Value |
| --- | --- |
| `collected:` | 2026-06-30 |
| `source:` | Manual extraction from each region's `/f3-nation-settings` admin list |
| `collected_by:` | Project maintainer (manual extraction) |
| `fidelity:` | `system-extracted` |
| `coverage:` | Puget Sound, Cascades, Kirkland, Tundra, Seattle, North Sea; Redmond not supplied |
| `known_gaps:` | Redmond F3-Nation app admin data was not supplied; names are display/F3 names and may not map cleanly to Slack user IDs without additional matching |
| `refresh_trigger:` | A region's admin list changes in `/f3-nation-settings`, or Redmond data becomes available |
| `refresh_owner:` | Project maintainer |

Apply the `fidelity` value above using the table in [query-policy.md](../query-policy.md#dated-augmentation-evidence): `system-extracted` supports `High` for its collection date, and resolves as `Contested` against conflicting dated Slack evidence (this roster stated first if newer).

This roster does not imply Slack workspace administration, AO/Site Q ownership, or regional SLT status — see [f3-nation-operations.md §Critical role distinctions](f3-nation-operations.md#critical-role-distinctions).

## Roster

| Region | Workspace | F3-Nation app admins | Notes |
|---|---|---|---|
| Puget Sound | `f3pugetsound` | CornFed; Voltaire; Sherpa; Columbia - Cascades Region Nantan; Schedule 1 | Bot/org admins, not necessarily Slack admins |
| Cascades | `f3cascades` | Radar; Columbia; Bunt; Flexo; Bunny | Bunt appeared twice in the supplied list and was de-duplicated |
| Kirkland | `f3kirkland` | Amadeus; Falsetto; Thimble; Crashdummy; Speedo; Sunflower; Retread; Montoya; skynet; Papercut; Voltaire; Indy; Pegleg (Seattle); Pogo; Needles; Tardy - Kirkland 3rd F | Bot/org admins, not necessarily Slack admins |
| Tundra | `f3tundra` | Moa; RBI; DreamWeaver; beltway; Snips; Jalapeño Tundra Nan'tan; Voltaire; Tinker Toy; Brexit; Moneypuck; LumberMack; Greywater; Pegleg (Seattle); MooseJaw; Salsa; schedule 1; cartwheel; Bugle; Hamm's | Lowercase `schedule 1` preserved from manual extraction; do not auto-merge with `Schedule 1` without confirmation |
| Seattle | `f3seattle` | Manual; Voltaire; Priceline; Doggy Paddle; Boo-Boo; Daisy Dukes; Oodles; Chum; Sea Level; Tap Out; Preroll; OldeEnglish; The Tank; Keystone; Bombadil; Turndown; WalkOn; Silicone; Palinka; Alimony; PumpNDump; Picante; Mr. Hand; Zima; Watson; Pylon; Pegleg; Cheese Coyote; Ipanema | Manual appeared twice in the supplied list and was de-duplicated |
| North Sea | `f3northsea` | Heeere's Johnny; Voltaire; Bueller - Weaselshaker; sharkweek; Silo Nan'tan; Peekaboo | Bot/org admins, not necessarily Slack admins |
| Redmond | `f3redmond` | Not provided | Do not infer Redmond F3-Nation app admins from Slack admins, Puget Sound admins, leadership titles, or activity patterns |

## Limitations

- Names are display/F3 names as manually extracted and may not map cleanly to Slack user IDs without additional matching.
- Do not merge workspace-local people solely by similar names unless the digest/profile data strongly supports the match.
- Visible Slack activity does not prove who handled issues in DMs, private channels, in-person conversations, or channels missing from the export.
- Redmond F3-Nation app admin data was not supplied.
