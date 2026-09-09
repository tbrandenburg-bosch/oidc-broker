# oidc-broker

PoC implementation of the plan in [`docs/INITIAL.md`](docs/INITIAL.md):
exchange a real GitHub Actions OIDC JWT for a user-scoped GitHub token via a
local broker. Everything stays within this account/repo.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in secrets/values (see below)
```

Required `.env` values (see `.env.example` for the full list):
- `GITHUB_APP_CLIENT_ID`, `GITHUB_APP_CLIENT_SECRET` — from the registered
  GitHub App (docs/INITIAL.md Step 1)
- `EXPECTED_REPOSITORY` — `owner/repo` of this repository
- `EXPECTED_REF` — the exact feature branch ref the workflow runs on, e.g.
  `refs/heads/my-feature`
- `ALLOWED_ACTOR_IDS` — comma-separated GitHub user id(s) allowed through
  the broker (get your id after running the consent step, or via
  `gh api user --jq .id`)

## Run the PoC

1. **One-time user consent** (opens a browser, needs manual approval):
   ```bash
   python -m broker.consent
   ```
   Prints your GitHub user id — add it to `ALLOWED_ACTOR_IDS` in `.env`.

2. **Start the broker:**
   ```bash
   python -m broker.server
   ```
   Listens on `http://localhost:9000` (`/mint`).

3. **Expose it publicly** (separate terminal):
   ```bash
   ngrok http 9000
   ```
   Note the printed HTTPS URL.

4. **Set the repo secret** with that URL:
   ```bash
   gh secret set POC_BROKER_URL --body "https://<your-ngrok-subdomain>.ngrok-free.app"
   ```

5. **Push the feature branch** containing
   `.github/workflows/poc-mint.yml` and trigger it:
   ```bash
   gh workflow run poc-mint.yml --ref <your-feature-branch>
   ```

6. **Prove attribution** — see docs/INITIAL.md Step 6.

## Cleanup

Follow the mandatory checklist in docs/INITIAL.md before closing the PoC
(remove workflow step, delete secret, revoke app authorization, stop
tunnel/broker, delete `.data/refresh_tokens.json`).
