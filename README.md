# Sutradhar: an expert-call booking agent

ContextCon 04, IIT Kanpur. Team: Aditya, Sunil, Deepak.

## Run
    cd backend && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
    cp ../.env.example ../.env   # fill keys
    uvicorn backend.app.main:app --port 8000 --reload   # run from repo root

## What the data can and cannot do
Crustdata does not know who consented, who is available, or what they charge.
The expert pool is opt-in (onboarding form). Crustdata Person Enrich is used only to verify claimed work history.

The claims on Test Profile A–D were written by our team for testing. The real people behind those profiles never made these claims.

(More to be added at 6 AM.)
