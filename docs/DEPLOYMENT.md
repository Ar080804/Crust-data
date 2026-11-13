# Sutradhar deployment

The public demo replays newly authored fictional profiles in the browser. The public examples have no contact information, profile links or individual employment histories. The `vercel-deploy` branch also packages the FastAPI API and one optional Telegram worker. The API and worker share PostgreSQL. Local development continues to use SQLite when `DATABASE_URL` is empty.

## Vercel project setup

1. Use the **repository root** for the full stack and the root `vercel.json` for service routing. The original frontend-only deployment uses `frontend/` as its root.
2. Keep `VITE_MOCK=true` for the public demo. For live mode set `VITE_MOCK=false`, `VITE_API_URL=/api`, and `APP_URL` to the production HTTPS origin. Register exactly `<APP_URL>/api/auth/google/callback` on a Google OAuth **Web application** client.
3. Set `DATABASE_URL` to a pooled PostgreSQL connection string. Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `TELEGRAM_BOT_TOKEN` and `GOOGLE_CALENDAR_TOKEN_JSON` in Vercel’s production environment. The last variable contains the Calendar account’s refreshable authorized-user JSON. Keep all secret values server-side. The requester’s verified email receives the invite.
4. The cloud starts with an empty expert pool. Supply explicitly opted-in experts with current slots using the server-side `EXPERT_POOL_JSON` setting. The old hackathon slots end on 8 November 2026. Simulated profiles and placeholder contacts are excluded from cloud outreach. LinkedIn onboarding can be added separately with `VITE_ONBOARDING_URL`.
5. `ANTHROPIC_API_KEY` enables the model parser. `CRUSTDATA_API_KEY` enables fresh verification on cache misses. Cloud verification caches fresh results in the database. The original roster and historical profile cache stay out of the build. The rule-based parser works without an API key.
6. Deploy the complete app. Confirm `/api/health` reports the database ready, stop any other poller using the same Telegram token, then scale `worker` to **one** production instance. Its committed initial count is zero so publishing the portfolio does not consume worker quota. Vercel Hobby meters reserved memory even while the worker waits. [Vercel daemon limits](https://vercel.com/docs/daemons/limits)

## Activate the homepage sign-in buttons

The home page shows Google for users and Telegram for experts. Sign-in availability is independent of `VITE_MOCK`, which selects the booking experience. Configure a reachable production `DATABASE_URL` and set `APP_URL=https://sutradhar-kappa.vercel.app` to store sessions for either provider. Supply each provider's own credentials only on the server.

| Account | Vercel production variables | Register this redirect URL |
|---|---|---|
| Google user | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` from a Google OAuth Web application | `https://sutradhar-kappa.vercel.app/api/auth/google/callback` |
| Telegram expert | `TELEGRAM_CLIENT_ID`, `TELEGRAM_CLIENT_SECRET` from BotFather’s Web Login settings, using the default RS256 signing algorithm | `https://sutradhar-kappa.vercel.app/api/auth/telegram/callback` |

In BotFather, also add the public site origin to Allowed URLs. Redeploy after editing environment variables and check `/api/auth/providers` for the two availability flags. The Telegram booking bot token is used for outreach. Telegram sign-in establishes identity only. Enrolling an expert for real bookings uses the separate opt-in onboarding flow.

[Google OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect) · [Telegram Web Login](https://core.telegram.org/bots/telegram-login)

## Test a real booking

Use two consenting test accounts and an available future slot. Sign in, create a request, reply to the bot and verify the event and attendees in the test calendar. Confirm the request survives a worker restart. The hosted API requires a Google session and checks request ownership. Development-only endpoints are available locally.

For a local API and separate worker, run `RUN_WORKER_IN_API=0 uvicorn backend.app.main:app --port 8000` and `python -m backend.worker` from the repo root. `vercel dev` and Vercel previews do not start a daemon. Point local processes at the same test database and use a separate test bot.
