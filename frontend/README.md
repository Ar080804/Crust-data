# Frontend (owner: Deepak)

Setup: `npm create vite@latest . -- --template react-ts`, then `npm install`.

- Port 5173. Backend URL comes from `VITE_API_URL=http://localhost:8000`.
- `VITE_MOCK=true` makes the UI read `../contract/fixtures/*.json` instead of the API.
- Poll `GET /requests/{id}` every 1s. No SSE or websockets.
- Only Deepak edits `package.json`.
