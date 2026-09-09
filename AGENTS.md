# AGENTS.md — oidc-broker

Guidance for AI agents (and humans) working in this repo, based on pitfalls
actually hit while building and running this PoC.

## What this repo is

A PoC broker that exchanges a GitHub Actions OIDC JWT for a user-scoped
GitHub token (`ghu_...`). See `README.md` for the concept, `docs/INITIAL.md`
for the original detailed plan.

## Environment facts

- Broker: Python 3.12, Flask, PyJWT, requests — see `requirements.txt`
- Local dev venv used in this session: `/tmp/opencode/venv`
- `.env` holds all secrets (GitHub Client Secret, ngrok authtoken) — never
  commit it, never `cat`/`Read` it if you can avoid it (see below)
- `gh` CLI is pre-authenticated with `repo`+`workflow` scopes on
  `tbrandenburg-bosch` — safe to use for `gh secret set`, `gh workflow run`,
  `gh run view`, etc.

## Pitfalls discovered this session (read before touching process management)

### 1. `pkill -f <pattern>` can kill its own wrapper process
If the pattern you pass to `pkill -f` literally appears in the *invoking*
`bash -c "..."` command line (it always does, since you just typed it),
`pkill` may match and kill that wrapper too — not just your target. This
caused every "kill the broker" command to hang/wedge the shell session.

**Fix:** never `pkill -f "exact substring you just typed"`. Instead, filter
matched PIDs by excluding the current shell's own PID:
```bash
self=$$
for p in $(pgrep -f "broker.server"); do
  [ "$p" != "$self" ] && kill "$p"
done
```

### 2. Backgrounding a process without full detachment wedges the tool session
`cmd > file 2>&1 & disown` is not enough in some sandboxed shell-tool
environments — the wrapper can still block on a shared pipe/job-control
notification. **Fix:** wrap the whole thing in a subshell so no job is ever
registered in the persistent session's job table, and redirect stdin too:
```bash
( setsid your_long_running_cmd </dev/null >logfile 2>&1 & )
```

### 3. Python buffers stdout when not attached to a TTY
Background processes redirected to a log file may show **no output at all**
for a long time, even though they're actively running — Python fully
buffers stdout in that case. **Fix:** always run with `python -u` (or set
`PYTHONUNBUFFERED=1`) for anything you intend to `tail`/`cat` while it runs.

### 4. `threading.Lock()` is not reentrant — watch for self-deadlock
`token_store.save_refresh_token()` used to call `load()` from *inside* an
already-held `with _lock:` block. Since `Lock` (unlike `RLock`) cannot be
acquired twice by the same thread, this deadlocked **forever**, with no
exception, no timeout, no error — just silence. This looked exactly like a
network hang and cost significant time to diagnose.

**Lesson:** if a "network call" is hanging with zero output and a
configured `timeout=` isn't firing, suspect a **local deadlock** before
blaming the network. Add instrumentation (flushed prints) immediately
before/after every blocking call to bisect where execution actually stalls.

### 5. Never print/read files containing secrets into the conversation
`Read`-ing `.env` or printing a `Config` dataclass containing
`github_client_secret` / `NGROK_AUTHTOKEN` exposes the value in the chat
transcript. This happened twice in this session. **Always** edit `.env`
blindly (`Edit` tool with exact key= line replacement) and verify presence
with boolean checks (`grep -q "^KEY=.\+"`) instead of reading the file.

### 6. GitHub App: "authorize" ≠ "install"
A user can complete the OAuth *authorize* screen without the App being
*installed* on the target repo. Attempting to refresh a token before
installation gives a **fast, misleading** `bad_refresh_token` /
`incorrect or expired` error — not an installation-related message. If a
freshly-issued refresh token immediately fails, check
`https://github.com/settings/installations` before assuming a code/secret
bug.

### 7. OAuth codes are single-use and burn fast on client-side timeouts
If a code-exchange request hangs/times out on the client side, GitHub may
have still processed it server-side — the code is now burned even though
you got no response. Don't retry with the same code; get a fresh
authorize URL (fresh `state`) and redo the browser click.

### 8. ngrok free tier
- Requires an authtoken (`ngrok config add-authtoken` or `NGROK_AUTHTOKEN`
  env var) — no anonymous tunnels.
- Add `-H 'ngrok-skip-browser-warning: true'` to programmatic requests
  through the tunnel to avoid the anti-bot interstitial page.
- The reserved subdomain persists across restarts in the same session —
  don't assume you need to re-set `POC_BROKER_URL` after every tunnel
  restart; check if the URL is actually the same first.

### 9. Workflow debugging
- Add `--max-time N` to every `curl` in a workflow step, and
  `timeout-minutes:` on the job. Without these, a hung broker turns into a
  multi-minute+ stuck CI run with no useful signal.
- `echo "Got ID token, length: ${#ID_TOKEN}"` is a safe sanity check that
  doesn't leak the token but confirms the first leg of the chain worked.

## Before merging workflow/broker changes to `main`

- The PoC workflow (`.github/workflows/poc-mint.yml`) has an
  `if: github.ref != 'refs/heads/main'` guard and is `workflow_dispatch`
  only — safe to keep on `main`, but it becomes a dead no-op once
  `POC_BROKER_URL` is deleted and the tunnel/broker aren't running. Don't
  be surprised if someone re-triggers it later and it just fails on the
  curl to the broker — that's expected, not a regression.

## Secrets exposed during this session (rotate if this is ever a concern)

- `GITHUB_APP_CLIENT_SECRET` — printed once via a debug script
- `NGROK_AUTHTOKEN` — printed once via a `Read` of `.env`

Neither was rotated as of the last commit in this session (explicit user
decision). If picking this repo up later, check with the owner whether
rotation happened before treating these as trustworthy.
