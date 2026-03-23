# Run Web MVP Locally

## 1) Start everything in one command
1. `cd d:/Repos/WSSMEAS`
2. `./scripts/start_local_fast.ps1`
3. Open: `http://127.0.0.1:5173`

## 2) Stop local services
1. `cd d:/Repos/WSSMEAS`
2. `./scripts/stop_local_fast.ps1`

## 3) Manual mode (if needed)
1. Backend API: `d:/Repos/WSSMEAS/.venv/Scripts/python.exe d:/Repos/WSSMEAS/scripts/run_api_server.py`
2. Health check: `GET http://127.0.0.1:8000/api/health`
3. Frontend: `cd d:/Repos/WSSMEAS/web && npm run dev -- --host 127.0.0.1 --port 5173`

## 4) Demo flow
1. Login demo with email + password.
2. Complete company setup.
3. Post demo event from context panel.
4. Load financial and tax reports.
5. Switch to Advanced mode to inspect details.

## 5) Build and deploy prep
- Frontend build: `cd web && npm run build`
- API image build: use commands in [DEPLOY.md](DEPLOY.md)
- Firebase Hosting rewrite config is in [firebase.json](firebase.json)
