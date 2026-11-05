# Team rules (read once and follow)

| | Aditya | Sunil | Deepak |
|---|---|---|---|
| Owns | `backend/app/`, `contract/`, `backend/requirements.txt`, `.gitignore` | `backend/integrations/`, `backend/eval/`, `data/` | `frontend/`, `README.md`, the demo video |
| Job | FastAPI, SQLite state machine, LLM intake/negotiate, constraint checks, Calendar booking, resume | Crustdata verify, Telegram bot, pool seed, eval harness | UI, README, video |

1. Never edit a file in someone else's folder. Ask the owner instead.
2. Only Aditya changes `contract/`. Every change gets announced in the group.
3. Everyone works on `main`. Run `git pull --rebase && git push` every 30–45 minutes.
4. Never commit `.env`, `*.db` or `token.json`.
5. Only one laptop runs the real Telegram bot, otherwise Telegram returns 409 Conflict. Sunil uses a separate test bot.
6. The Google Calendar token lives only on Aditya's laptop. The final demo runs on Aditya's laptop.
7. Ports are fixed: backend 8000, frontend 5173.
8. Crustdata responses get cached in `data/crustdata_cache/<id>.json` and committed, so credits are only spent once.

## Checkpoints
- 1:30: curl a request and get back a shortlist with verification.
- 3:30: frontend switches to `MOCK=false` against the real backend, and the end-to-end flow works.
- 5:00: kill/resume works and the eval numbers are ready.
- 5:45: feature freeze. Record the video and write the README.
- 7:00: submit.

## Cut order if behind
duplicate merging → counter-offer → eval 10×3 → 429 retry.
Never cut: kill/resume, fake-claim catch, live phone reply, invite landing.
