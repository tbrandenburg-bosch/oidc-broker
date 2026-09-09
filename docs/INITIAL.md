# OIDC Token-Broker PoC — Implementation Plan

Goal: prove a full chain end-to-end using a *real* GitHub Actions OIDC JWT,
minted on a GitHub-hosted runner via a workflow in this repository, exchanged
by a local broker for a user-scoped GitHub token (`ghu_...`) attributed to a
real user — without ever cloning any target repo locally as part of the
exchange itself.

Everything in this PoC runs entirely within this account/repo. No other
organization, account, or infrastructure is involved.

## Prerequisites (check before starting)

1. Confirm you can push a feature branch to this repository and trigger a
   workflow on it.
2. Confirm the workflow runner has outbound internet access (needed to reach
   `token.actions.githubusercontent.com` for JWKS, and to reach the tunneled
   localhost broker). A GitHub-hosted runner (`ubuntu-latest`) satisfies this
   by default.
3. Confirm GitHub App creation is available on the account owning this repo
   (true for any personal GitHub account with no additional approval needed).

## Step 1 — Register a test GitHub App (one-time)

- Settings -> Developer settings -> GitHub Apps -> New GitHub App
- Callback URL: `http://localhost:8765/callback`
- Enable "Request user authorization (OAuth) during installation"
- Webhook: uncheck "Active" and leave the Webhook URL blank — this PoC's
  broker doesn't consume any GitHub webhook events, only the OAuth callback
  above. GitHub requires the Webhook URL field only when Active is checked.
- Permissions: minimal (e.g. Issues: write) just to prove attribution
- Install on this repository only

Registered app (identifiers only — Client Secret and private key are never
recorded here; store them in the local broker's secret storage only):

- Name: `btr8fe-oidc-broker`
- Owned by: `@tbrandenburg-bosch`
- App ID: `4887051`
- Client ID: `Iv23liUIsKcoWTlnBwXM`

## Step 2 — One-time user consent (localhost)

- Local script opens:
  `https://github.com/login/oauth/authorize?client_id=...&redirect_uri=http://localhost:8765/callback&state=...`
- Local `http.server` on :8765 catches `code`, exchanges for
  `{access_token, refresh_token}` via
  `POST https://github.com/login/oauth/access_token`
- Store `refresh_token` locally, keyed by the GitHub user id
  (`gh api user --jq .id`)

## Step 3 — Local broker (`localhost:9000/mint`)

Responsibilities:
- Accept a POSTed OIDC JWT
- Verify signature against `https://token.actions.githubusercontent.com/.well-known/jwks`
- Validate claims: `iss`, `aud` (custom audience string chosen for this PoC),
  `repository` (must match this repo), `ref` is the expected feature branch,
  `actor_id` is allow-listed
- Look up stored refresh token for that `actor_id`
- Exchange it: `POST https://github.com/login/oauth/access_token`
  `grant_type=refresh_token`
- Return the new user-scoped token (never log it)

## Step 4 — Expose broker publicly (tunnel)

```bash
ngrok http 9000
# or: cloudflared tunnel --url http://localhost:9000
```
Note the public HTTPS URL — the runner needs to reach it.

## Step 5 — Feature-branch workflow step

Add a job/step, only on a feature branch, guarded so it never merges to the
default branch:

```yaml
permissions:
  id-token: write
  contents: read
jobs:
  probe:
    runs-on: ubuntu-latest
    steps:
      - name: PoC — mint token via broker
        run: |
          set -euo pipefail
          ID_TOKEN=$(curl -sf -H "Authorization: Bearer ${ACTIONS_ID_TOKEN_REQUEST_TOKEN}" \
            "${ACTIONS_ID_TOKEN_REQUEST_URL}&audience=poc-broker" | jq -r .value)
          RESP=$(curl -sf -X POST "$BROKER_URL/mint" \
            -H 'Content-Type: application/json' \
            -d "{\"jwt\":\"${ID_TOKEN}\"}")
          echo "$RESP" | jq -r .expires_in   # sanity check only, never echo the token
        env:
          BROKER_URL: ${{ secrets.POC_BROKER_URL }}   # the tunnel URL, stored as a secret
```

Notes:
- `BROKER_URL` goes in as a repo secret so the tunnel URL (ephemeral,
  changes each run) isn't hardcoded in workflow source that gets committed.
- Never `echo` or log the returned token — mask it (`::add-mask::`)
  immediately if you need to reference it in later steps.

## Step 6 — Prove attribution

From the broker's side (or a follow-up step using the returned token against
this repository):

```bash
curl -H "Authorization: Bearer $TOKEN" https://api.github.com/user
# -> shows the real user, not a bot/service account

curl -X POST -H "Authorization: Bearer $TOKEN" \
  https://api.github.com/repos/<owner>/<repo>/issues/1/comments \
  -d '{"body":"posted via broker-minted token from the PoC workflow"}'
```
Check the comment's author on github.com.

## Cleanup checklist (mandatory before closing the PoC)

- [ ] Remove the temporary step from the workflow on the feature branch
      before any merge
- [ ] Delete the `POC_BROKER_URL` secret
- [ ] Revoke the GitHub App's installation / user authorization
      (Settings -> Applications -> Authorized GitHub Apps -> Revoke)
- [ ] Stop the tunnel and local broker process
- [ ] Delete locally stored refresh token file
- [ ] Confirm no token value appears in any workflow run log
      (Actions auto-masks known secrets, but only if registered as a
      `secrets.*` — raw curl output is not masked automatically)

## Verified environment facts

- A GitHub-hosted `ubuntu-latest` runner successfully executes jobs on this
  account (verified with a minimal `workflow_dispatch` probe job).
- No additional approvals, restrictions, or third-party policy gates apply
  when the entire chain (App, OAuth consent, workflow, broker) stays within
  this single account and repository.
</content>
</invoke>
