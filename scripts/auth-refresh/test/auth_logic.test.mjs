// Unit tests for the pure auth-refresh logic (AC6).
// Run: node --test  (from scripts/auth-refresh/)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  loadWorkspaces,
  parseXoxcTokens,
  pickSessionCookie,
  classifySession,
  buildRegisterArgs,
  matchWorkspaceToken,
} from '../auth_logic.mjs';

// --- loadWorkspaces (AC6): tokens.json object -> workspace name list ---
test('loadWorkspaces returns keys of the tokens map', () => {
  assert.deepEqual(
    loadWorkspaces({ f3cascades: 'xoxc-1', f3redmond: 'xoxc-2' }),
    ['f3cascades', 'f3redmond'],
  );
});

test('loadWorkspaces tolerates empty / non-object input', () => {
  assert.deepEqual(loadWorkspaces({}), []);
  assert.deepEqual(loadWorkspaces(null), []);
  assert.deepEqual(loadWorkspaces('nope'), []);
});

// --- parseXoxcTokens (AC3): localStorage.localConfig_v2 -> per-team tokens ---
test('parseXoxcTokens extracts token+name+teamId+domain per team', () => {
  const raw = JSON.stringify({
    teams: {
      T111: { name: 'F3 Cascades', team_id: 'T111', token: 'xoxc-aaa', url: 'https://f3cascades.slack.com/' },
      T222: { name: 'F3 Redmond', team_id: 'T222', token: 'xoxc-bbb', domain: 'f3redmond' },
    },
  });
  assert.deepEqual(parseXoxcTokens(raw), [
    { name: 'F3 Cascades', teamId: 'T111', token: 'xoxc-aaa', domain: 'f3cascades' },
    { name: 'F3 Redmond', teamId: 'T222', token: 'xoxc-bbb', domain: 'f3redmond' },
  ]);
});

test('parseXoxcTokens returns [] for malformed / empty input', () => {
  assert.deepEqual(parseXoxcTokens(undefined), []);
  assert.deepEqual(parseXoxcTokens('{not json'), []);
  assert.deepEqual(parseXoxcTokens(JSON.stringify({})), []);
});

// --- matchWorkspaceToken (AC3): map a workspace name to the right team's token ---
test('matchWorkspaceToken picks the team whose domain matches the workspace', () => {
  const teams = [
    { name: 'F3 Cascades', teamId: 'T111', token: 'xoxc-aaa', domain: 'f3cascades' },
    { name: 'F3 Redmond', teamId: 'T222', token: 'xoxc-bbb', domain: 'f3redmond' },
  ];
  assert.equal(matchWorkspaceToken(teams, 'f3redmond'), 'xoxc-bbb');
  assert.equal(matchWorkspaceToken(teams, 'f3redmond.slack.com'), 'xoxc-bbb');
});

test('matchWorkspaceToken falls back to the sole team, else null', () => {
  const one = [{ name: 'Only', teamId: 'T1', token: 'xoxc-solo', domain: 'whatever' }];
  assert.equal(matchWorkspaceToken(one, 'f3cascades'), 'xoxc-solo');
  const many = [
    { name: 'A', teamId: 'T1', token: 'xoxc-a', domain: 'aaa' },
    { name: 'B', teamId: 'T2', token: 'xoxc-b', domain: 'bbb' },
  ];
  assert.equal(matchWorkspaceToken(many, 'f3cascades'), null);
  assert.equal(matchWorkspaceToken([], 'f3cascades'), null);
});

// --- pickSessionCookie (AC3): find the HttpOnly xoxd 'd' cookie ---
test('pickSessionCookie returns the d cookie value on a slack.com domain', () => {
  const cookies = [
    { name: 'lc', value: 'x', domain: '.slack.com' },
    { name: 'd', value: 'xoxd-SECRET', domain: '.slack.com', httpOnly: true },
    { name: 'd', value: 'other', domain: '.example.com' },
  ];
  assert.equal(pickSessionCookie(cookies), 'xoxd-SECRET');
});

test('pickSessionCookie prefers the account-wide .slack.com cookie over a subdomain one', () => {
  const cookies = [
    { name: 'd', value: 'xoxd-SUBDOMAIN', domain: 'f3seattle.slack.com', httpOnly: true },
    { name: 'd', value: 'xoxd-ACCOUNT', domain: '.slack.com', httpOnly: true },
  ];
  assert.equal(pickSessionCookie(cookies), 'xoxd-ACCOUNT');
});

test('pickSessionCookie returns null when no d cookie present', () => {
  assert.equal(pickSessionCookie([{ name: 'x', value: '1', domain: '.slack.com' }]), null);
  assert.equal(pickSessionCookie([]), null);
});

// --- classifySession (AC1): probe result -> valid | stale | error ---
test('classifySession: exit 0 clean -> valid', () => {
  assert.equal(classifySession({ exitCode: 0, stderr: '' }), 'valid');
});

test('classifySession: expiry / relogin / auth-error stderr -> stale', () => {
  assert.equal(
    classifySession({ exitCode: 1, stderr: 'authentication details expired, relogin is necessary' }),
    'stale',
  );
  assert.equal(
    classifySession({ exitCode: 1, stderr: 'EZ-Login 3000 is not supported on this OS' }),
    'stale',
  );
  assert.equal(
    classifySession({ exitCode: 1, stderr: '004 (Authentication Error): auth error' }),
    'stale',
  );
});

test('classifySession: non-zero exit with unrelated stderr -> error', () => {
  assert.equal(classifySession({ exitCode: 2, stderr: 'network unreachable' }), 'error');
});

// --- buildRegisterArgs (AC4): slackdump argv for headless registration ---
test('buildRegisterArgs builds the workspace-new argv', () => {
  assert.deepEqual(
    buildRegisterArgs('f3cascades', 'xoxc-aaa', 'xoxd-SECRET'),
    ['workspace', 'new', '-token', 'xoxc-aaa', '-cookie', 'xoxd-SECRET', 'f3cascades'],
  );
});
