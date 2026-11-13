# Sutradhar deployment

The public demo replays newly authored fictional profiles in the browser. The public examples have no contact information, profile links or individual employment histories. The `vercel-deploy` branch also packages the FastAPI API and one optional Telegram worker. The API and worker share PostgreSQL. Local development continues to use SQLite when `DATABASE_URL` is empty.

## Vercel project setup

1. Use the **repository root** for the full stack and the root `vercel.json` for service routing. The original frontend-only deployment uses `frontend/` as its root.
2. Keep `VITE_MOCK=true` for the public demo. For live mode set `VITE_MOCK=false`, `VITE_API_URL=/api`, and `APP_URL` to the production HTTPS origin. Register exactly `<APP_URL>/api/auth/google/callback` on a Google OAuth **Web application** client.
3. Set `DATABASE_URL` to a pooled PostgreSQL connection string. Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `TELEGRAM_BOT_TOKEN` and `GOOGLE_CALENDAR_TOKEN_JSON` in Vercel’s production environment. The last variable contains the Calendar account’s refreshable authorized-user JSON. Keep all secret values server-side. The requester’s verified email receives the invite.
4. The cloud starts with an empty expert pool. Supply explicitly opted-in experts with current slots using the server-side `EXPERT_POOL_JSON` setting. The old hackathon slots end on 8 November 2026. Simulated profiles and placeholder contacts are excluded from cloud outreach. LinkedIn onboarding can be added separately with `VITE_ONBOARDING_URL`.
5. `ANTHROPIC_API_KEY` enables the model parser. `CRUSTDATA_API_KEY` enables fresh verification on cache misses. Cloud verification caches fresh results in the database. The original roster and historical profile cache stay out of the build. The rule-based parser works without an API key.
6. Deploy the complete app. Confirm `/api/health` reports the database ready, stop any other poller using the same Telegram token, then scale `worker` to **one** production instance. Its committed initial count is zero so publishing the portfolio does not consume worker quota. Vercel Hobby meters reserved memory even while the worker waits. [Vercel daemon limits](https://vercel.com/docs/daemons/limits)

## Activate user and expert login

Select **Login** in the site header to open `/login`. The page offers Google for users and LinkedIn for experts. The `VITE_MOCK` setting controls the booking demo independently. Either provider needs a reachable production `DATABASE_URL` and `APP_URL=https://sutradhar-kappa.vercel.app` to issue sessions. Set client secrets in the server environment.

| Account | Vercel production settings | Authorized redirect URL |
|---|---|---|
| Google user | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` for a Web application | `https://sutradhar-kappa.vercel.app/api/auth/google/callback` |
| LinkedIn expert | `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET` for the LinkedIn developer app | `https://sutradhar-kappa.vercel.app/api/auth/linkedin/callback` |

In the LinkedIn developer app, enable **Sign In with LinkedIn using OpenID Connect** under Products and register the redirect URL under Auth. Redeploy after editing environment variables. `/api/auth/providers` returns a boolean for each provider. LinkedIn sign-in connects the member account. The separate onboarding service checks professional claims through Crustdata and links Telegram for booking messages. Set `VITE_ONBOARDING_URL` to that service when available.

[Google OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect) · [LinkedIn OpenID Connect](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/sign-in-with-linkedin-v2)

## Test a real booking

Use two consenting test accounts and an available future slot. Sign in, create a request, reply to the bot and verify the event and attendees in the test calendar. Confirm the request survives a worker restart. The hosted API requires a Google session and checks request ownership. Development-only endpoints are available locally.

For a local API and separate worker, run `RUN_WORKER_IN_API=0 uvicorn backend.app.main:app --port 8000` and `python -m backend.worker` from the repo root. `vercel dev` and Vercel previews do not start a daemon. Point local processes at the same test database and use a separate test bot.
