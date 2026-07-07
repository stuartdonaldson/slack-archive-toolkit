#!/usr/bin/env node
/**
 * One-command Slack auth refresh (bd SlackBackup-fac).
 *
 * Probes every workspace in ~/.slackdump-tokens.json, opens a persistent Chromium
 * profile ONLY for the ones whose session has expired, lets you log in by hand
 * (SSO / 2FA and all), then reads the xoxc token (localStorage) + xoxd `d` cookie
 * (cookie jar) and re-registers each via `slackdump workspace new -token -cookie`.
 *
 * The persistent profile means valid logins survive between runs, so most runs
 * prompt you for nothing. No admin rights and no app install required — this is the
 * plain browser-session method, just automated end to end.
 *
 * Env (set in .envrc):
 *   SLACKDUMP_AUTH_PROFILE  persistent Chromium user-data-dir (required for reuse)
 *   SLACKDUMP_TOKENS        tokens.json path (default ~/.slackdump-tokens.json)
 *   SLACKDUMP_BIN           slackdump binary (default 'slackdump')
 *
 * Flags:
 *   --dry-run   print the register commands, call nothing (AC4)
 *   --all       refresh every workspace, not just the stale ones (AC5 override)
 *
 * The xoxd cookie is only ever held in memory and passed inline to slackdump —
 * never written to disk by this helper (AC7).
 */
import { chromium } from '@playwright/test';
import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import readline from 'node:readline';
import {
  loadWorkspaces,
  parseXoxcTokens,
  pickSessionCookie,
  classifySession,
  buildRegisterArgs,
  matchWorkspaceToken,
} from './auth_logic.mjs';

const DRY_RUN = process.argv.includes('--dry-run');
const ALL = process.argv.includes('--all');
const KEEPALIVE = process.argv.includes('--keepalive');
const TOKENS_PATH = process.env.SLACKDUMP_TOKENS || path.join(os.homedir(), '.slackdump-tokens.json');
const PROFILE_DIR = process.env.SLACKDUMP_AUTH_PROFILE || path.join(os.homedir(), '.cache', 'slackdump-auth-profile');
const SLACKDUMP = process.env.SLACKDUMP_BIN || 'slackdump';

const redact = (s) => (s ? `${s.slice(0, 10)}…(${s.length} chars)` : '<none>');

function ask(question) {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((resolve) => rl.question(question, (a) => { rl.close(); resolve(a); }));
}

/** Read Slack's `localConfig_v2` (all teams' tokens) from the logged-in browser.
 *  Prefers a page we already have; falls back to a fresh app.slack.com page. */
async function readLocalConfig(context, page) {
  const read = (p) => p.evaluate(() => window.localStorage.getItem('localConfig_v2')).catch(() => null);
  let raw = page ? await read(page) : null;
  if (!raw) {
    const p = await context.newPage();
    await p.goto('https://app.slack.com/', { waitUntil: 'domcontentloaded' }).catch(() => {});
    raw = await read(p);
  }
  return raw;
}

/** AC1: probe one workspace's live session via slackdump. */
function probe(ws) {
  const r = spawnSync(SLACKDUMP, ['list', 'channels', '-member-only', '-workspace', ws], { encoding: 'utf8' });
  const stderr = (r.stderr || '') + (r.error ? String(r.error) : '');
  return classifySession({ exitCode: r.status ?? 1, stderr });
}

/** AC4: register (or, under --dry-run, just print). */
function register(ws, token, cookie) {
  const args = buildRegisterArgs(ws, token, cookie);
  if (DRY_RUN) {
    console.log(`  [dry-run] ${SLACKDUMP} ${args.map((a) => (a === token ? redact(token) : a === cookie ? redact(cookie) : a)).join(' ')}`);
    return true;
  }
  // slackdump prompts "Overwrite? (y/N)" when the workspace already exists. Feed
  // 'y' on stdin so registration is non-interactive (headless keepalive has no TTY
  // — an inherited stdin there hits EOF and re-prompts forever). timeout is a
  // runaway guard against any other unexpected prompt.
  const r = spawnSync(SLACKDUMP, args, { input: 'y\n', stdio: ['pipe', 'inherit', 'inherit'], timeout: 120000 });
  return (r.status ?? 1) === 0;
}

/**
 * Non-interactive keep-alive (bd SlackBackup-5df). Slack rotates the session
 * cookie forward; the browser profile follows the rotation, slackdump does not.
 * This headlessly loads the Slack client on the persistent profile (keeping the
 * session active and picking up any rotation), then re-registers every workspace
 * whose team is present in the profile with the current shared cookie — so
 * slackdump never falls behind. Meant to run on a schedule; no prompts.
 */
async function keepAlive() {
  const tokens = JSON.parse(readFileSync(TOKENS_PATH, 'utf8'));
  const workspaces = loadWorkspaces(tokens);
  console.log(`Keep-alive (headless): profile ${PROFILE_DIR}, up to ${workspaces.length} workspace(s).`);

  const context = await chromium.launchPersistentContext(PROFILE_DIR, { headless: true });

  // Cookie value before we navigate anywhere (AC4 baseline).
  const before = pickSessionCookie(await context.cookies());

  // Load the Slack web client to keep the session active and pick up any pending
  // rotation, then give it a moment to make its boot/auth calls (AC2).
  const page = await context.newPage();
  await page.goto('https://app.slack.com/', { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => {});
  await page.waitForTimeout(8000);

  const after = pickSessionCookie(await context.cookies());
  const teams = parseXoxcTokens(await readLocalConfig(context, page));

  console.log(`  cookie ${before === after ? 'unchanged this run' : 'ROTATED this run'} — before=${redact(before)} after=${redact(after)}`);
  console.log(`  teams in profile: ${teams.length}`);
  if (!after || teams.length === 0) {
    console.error('Keep-alive: profile appears logged out (no cookie / no teams) — run `npm run refresh` interactively.');
    await context.close();
    process.exit(1);
  }

  let ok = 0;
  let matched = 0;
  for (const ws of workspaces) {
    const token = matchWorkspaceToken(teams, ws);
    if (!token) continue; // team not logged in on this profile — leave it alone
    matched += 1;
    if (register(ws, token, after)) ok += 1;
  }

  await context.close();
  console.log(`Keep-alive done: ${ok}/${matched} profile-present workspace(s) ${DRY_RUN ? 'would be ' : ''}re-registered (of ${workspaces.length} total).`);
  process.exit(matched > 0 && ok === matched ? 0 : 1);
}

async function main() {
  const tokens = JSON.parse(readFileSync(TOKENS_PATH, 'utf8'));
  const workspaces = loadWorkspaces(tokens);
  if (workspaces.length === 0) {
    console.error(`No workspaces found in ${TOKENS_PATH}`);
    process.exit(1);
  }

  console.log(`Probing ${workspaces.length} workspace session(s)…`);
  const needing = [];
  for (const ws of workspaces) {
    const state = ALL ? 'stale' : probe(ws);
    const mark = state === 'valid' ? 'OK' : state === 'stale' ? 'NEEDS LOGIN' : 'ERROR (skipped)';
    console.log(`  ${ws.padEnd(24)} ${mark}`);
    if (state === 'stale') needing.push(ws);
  }

  if (needing.length === 0) {
    console.log('\nAll sessions valid — nothing to refresh.');
    return;
  }

  console.log(`\n${needing.length} workspace(s) need re-auth. Opening browser (profile: ${PROFILE_DIR}).`);
  console.log('Note: Slack rotates the shared session cookie on each login, so credentials');
  console.log('are captured only AFTER you have logged into every workspace below.\n');
  const context = await chromium.launchPersistentContext(PROFILE_DIR, {
    headless: false,
    args: ['--disable-blink-features=AutomationControlled'],
  });

  // Phase 1 — log into each stale workspace. Deliberately capture nothing yet:
  // each login can re-issue the account-wide `d` cookie, so anything captured
  // mid-loop would be invalidated by a later login (only the last would survive —
  // the exact bug this ordering fixes).
  let lastPage = null;
  for (const ws of needing) {
    const slug = ws.split('.')[0];
    const page = await context.newPage();
    await page.goto(`https://${slug}.slack.com/`, { waitUntil: 'domcontentloaded' }).catch(() => {});
    await ask(`>> Log into '${ws}' in the browser, wait for the workspace to load, then press ENTER… `);
    lastPage = page;
  }

  // Phase 2 — now that every workspace is logged in, capture ONCE: all team tokens
  // from localStorage plus the single, current shared cookie.
  const teams = parseXoxcTokens(await readLocalConfig(context, lastPage));
  const cookie = pickSessionCookie(await context.cookies());
  if (teams.length === 0) {
    console.error('\nCould not read any Slack teams from localStorage — is the browser logged in?');
  }
  if (!cookie) {
    console.error('\nCould not read the Slack `d` cookie — is the browser logged in?');
  }

  // Phase 3 — register every workspace with its token + the one shared cookie.
  console.log('');
  let ok = 0;
  for (const ws of needing) {
    const token = matchWorkspaceToken(teams, ws);
    if (!token || !cookie) {
      console.error(`  ✗ ${ws}: missing ${!token ? 'token (no matching team in localStorage)' : ''}${!token && !cookie ? ' + ' : ''}${!cookie ? 'cookie' : ''} — skipped.`);
      if (!token && teams.length > 0) {
        console.error(`     teams seen: ${teams.map((t) => t.domain || t.name).join(', ')}`);
      }
      continue;
    }
    console.log(`  ${ws}: token=${redact(token)} cookie=${redact(cookie)}`);
    if (register(ws, token, cookie)) ok += 1;
  }

  await context.close();
  console.log(`\nDone: ${ok}/${needing.length} workspace(s) ${DRY_RUN ? 'would be ' : ''}re-registered.`);
  if (ok < needing.length) {
    console.log('Re-run `npm run refresh` to retry any that were skipped.');
  }
}

(KEEPALIVE ? keepAlive() : main()).catch((err) => { console.error('refresh-auth failed:', err); process.exit(1); });
