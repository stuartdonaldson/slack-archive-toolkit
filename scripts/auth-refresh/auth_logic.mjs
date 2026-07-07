// Pure logic for the auth-refresh helper (AC6): no I/O, no Playwright, no process
// spawning — all of that lives in refresh-auth.mjs. These functions are unit-tested
// in test/auth_logic.test.mjs.

/** AC6: tokens.json object ({workspace: xoxc-token}) -> ordered workspace names. */
export function loadWorkspaces(tokens) {
  if (!tokens || typeof tokens !== 'object' || Array.isArray(tokens)) return [];
  return Object.keys(tokens);
}

/**
 * AC3: parse Slack's localStorage `localConfig_v2` JSON into per-team credentials.
 * Shape: { teams: { <teamId>: { name, team_id, token } } }. Returns [] on anything
 * malformed so a single bad workspace can't abort the run.
 */
export function parseXoxcTokens(localConfigRaw) {
  if (typeof localConfigRaw !== 'string' || localConfigRaw.length === 0) return [];
  let parsed;
  try {
    parsed = JSON.parse(localConfigRaw);
  } catch {
    return [];
  }
  const teams = parsed && parsed.teams;
  if (!teams || typeof teams !== 'object') return [];
  return Object.values(teams)
    .filter((t) => t && typeof t.token === 'string')
    .map((t) => ({
      name: t.name ?? null,
      teamId: t.team_id ?? null,
      token: t.token,
      domain: teamDomain(t),
    }));
}

/** Derive a bare workspace slug from a team's url (host's first label) or domain field. */
function teamDomain(team) {
  if (typeof team.url === 'string') {
    try {
      return new URL(team.url).hostname.split('.')[0] || null;
    } catch {
      /* fall through */
    }
  }
  if (typeof team.domain === 'string') return team.domain;
  return null;
}

/**
 * AC3: resolve which team's xoxc token belongs to `workspace`. Matches by domain
 * slug (workspace may be given as 'f3redmond' or 'f3redmond.slack.com'). Falls back
 * to the sole team when there is exactly one; returns null when ambiguous.
 */
export function matchWorkspaceToken(teams, workspace) {
  if (!Array.isArray(teams) || teams.length === 0) return null;
  const slug = String(workspace).split('.')[0].toLowerCase();
  const hit = teams.find((t) => t.domain && t.domain.toLowerCase() === slug);
  if (hit) return hit.token;
  return teams.length === 1 ? teams[0].token : null;
}

/**
 * AC3: pick the HttpOnly session cookie (`d`) for a Slack domain from a Playwright
 * cookie jar. JS in the page can't read this cookie; Playwright's context.cookies()
 * can. Returns the value, or null if absent.
 */
export function pickSessionCookie(cookies, { name = 'd' } = {}) {
  if (!Array.isArray(cookies)) return null;
  const matches = cookies.filter(
    (c) => c && c.name === name && typeof c.domain === 'string' && c.domain.includes('slack.com'),
  );
  if (matches.length === 0) return null;
  // Prefer the account-wide cookie on `.slack.com` (the one shared across every
  // workspace) over any workspace-subdomain-scoped `d` cookie.
  const account = matches.find((c) => c.domain === '.slack.com' || c.domain === 'slack.com');
  return (account || matches[0]).value;
}

// stderr signatures that mean "the session is dead, re-login required" (AC1).
const STALE_PATTERNS = [
  /authentication details expired/i,
  /relogin is necessary/i,
  /ez-login 3000/i,
  /authentication error/i,
  /invalid.*(auth|token|cookie)/i,
];

/**
 * AC1: classify a `slackdump list channels` probe result.
 *  - 'valid': exit 0.
 *  - 'stale': a known expiry/auth-failure signature (re-login will fix it).
 *  - 'error': failed for some other reason (network etc.) — do not prompt login.
 */
export function classifySession({ exitCode, stderr = '' } = {}) {
  if (exitCode === 0) return 'valid';
  if (STALE_PATTERNS.some((re) => re.test(stderr))) return 'stale';
  return 'error';
}

/** AC4: argv for headless registration — no browser, no cookie written to disk. */
export function buildRegisterArgs(workspace, token, cookie) {
  return ['workspace', 'new', '-token', token, '-cookie', cookie, workspace];
}
