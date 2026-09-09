# oidc-broker

A small proof-of-concept that answers one question: **can a GitHub Actions
workflow exchange its built-in OIDC identity for a token that acts as a real
human user** — instead of a bot/service account — **without ever storing a
long-lived credential in the workflow itself?**

Answer: yes. This repo shows exactly how.

## The idea, in plain terms

1. GitHub Actions can mint a short-lived, signed **ID token (JWT)** for any
   workflow run, for free, with no extra setup. It's the same mechanism
   cloud providers use for "OIDC login" instead of storing cloud secrets in
   CI. Nobody but GitHub can forge this token.
2. That JWT proves *"this exact workflow run, on this exact repo/branch,
   really is happening right now"* — but it doesn't grant access to
   anything by itself.
3. We stand up a small **broker** (a tiny local web server) that:
   - Checks the JWT is genuinely signed by GitHub (not forged)
   - Checks it's for *this* repo, *this* branch, and an allow-listed user
   - If everything checks out, hands back a **real GitHub token, scoped to
     a human user** — obtained once via a one-time browser login, then
     silently refreshed each time it's needed
4. The workflow uses that token to act on GitHub *as that person* — e.g.
   post an issue comment that shows up with their name and avatar, not a
   bot's.

```
 GitHub Actions run                    Your machine
┌─────────────────────┐         ┌───────────────────────────┐
│ 1. mint OIDC JWT     │──POST──▶│ 2. broker verifies JWT     │
│    (built-in,free)   │  /mint  │    + returns a user token  │
└─────────────────────┘         └───────────────────────────┘
                                          ▲
                                          │ one-time browser login
                                          │ (Step 2, done once)
                                     you, the human
```

## What's in this repo

| Path | What it does |
|---|---|
| `broker/consent.py` | Run **once**: opens your browser, you click "Authorize", it stores a refresh token for your GitHub user id. |
| `broker/server.py` | The broker itself. Verifies incoming JWTs and mints tokens on request. |
| `broker/config.py` | Reads all settings from `.env`. |
| `broker/token_store.py` | Tiny local file that remembers your refresh token (owner-only file permissions). |
| `.github/workflows/poc-mint.yml` | The workflow step that requests a JWT and calls the broker. Only runs when manually triggered, and refuses to run on `main`. |
| `docs/INITIAL.md` | The original detailed step-by-step plan this was built from. |

## Try it yourself

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in the values below
```

Fill in `.env`:
- `GITHUB_APP_ID`, `GITHUB_APP_CLIENT_ID`, `GITHUB_APP_CLIENT_SECRET` — from
  a GitHub App you register yourself (see `docs/INITIAL.md` Step 1)
- `EXPECTED_REPOSITORY` — `owner/repo` of this repo
- `EXPECTED_REF` — the exact branch the workflow will run on
- `ALLOWED_ACTOR_IDS` — your GitHub user id (printed after step 1 below)

**1. One-time login** (do this once, needs a real browser):
```bash
python -m broker.consent
```

**2. Start the broker:**
```bash
python -m broker.server
```

**3. Make it reachable from GitHub's servers** (separate terminal):
```bash
ngrok http 9000
```
Copy the `https://...ngrok...` URL it prints.

**4. Tell the workflow where to find it:**
```bash
gh secret set POC_BROKER_URL --body "https://<your-ngrok-url>"
```

**5. Run it:**
```bash
gh workflow run poc-mint.yml --ref <your-branch>
```

The workflow fetches a token from the broker and prints only its
`expires_in` (never the token itself) as a sanity check.

## Why this matters

Normally, giving a CI job the ability to "act as a user" means storing a
long-lived personal access token as a secret — if that secret leaks, it's
valid until manually revoked. Here, nothing long-lived ever touches the
workflow: the JWT is minted fresh per run and expires in minutes, and the
actual user token never leaves the broker except as a short-lived response
used immediately.

## Cleanup

This is a PoC, not a running service. When you're done experimenting:
- Stop the broker and `ngrok` processes
- `gh secret delete POC_BROKER_URL`
- Revoke the GitHub App's authorization: https://github.com/settings/applications
- Delete `.data/refresh_tokens.json`

Full checklist: see `docs/INITIAL.md`.
