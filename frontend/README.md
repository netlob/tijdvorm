## tijdvorm eastereggs frontend

### Run (dev)

1) Start the API server (in repo root):

```bash
pip install -r requirements-web.txt
uvicorn server:app --host 0.0.0.0 --port 8000
```

2) Start the frontend (in `frontend/`):

```bash
npm install
npm run dev
```

### Point the frontend at your homelab API (optional)

By default the frontend will call the Python API at `http://mini.netlob:8000` (CORS is enabled in the API).

If your API is on a different host/port:

- Create `frontend/.env.local`
- Set:
  - `VITE_API_HOST=http://mini.netlob:8000` (or whatever you use)

Then open the UI:
- From your laptop: `http://localhost:5173`
- From your phone (same network): `http://<your-computer-ip>:5173`


