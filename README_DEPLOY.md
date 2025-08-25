# QR Attendance — One-Click Deploy Guide

This folder is ready to deploy on Render/Railway/Heroku or run locally.

## Files added
- `wsgi.py` — initializes SQLite DB on first run when using Gunicorn.
- `Procfile` — start command for WSGI hosts.
- `runtime.txt` — suggested Python version.
- `requirements.txt` — updated to include `gunicorn`.

## A) Deploy to Render (free)
1. Push this folder to a **public GitHub repo** (or import directly in Render).
2. On https://render.com → *New* → **Web Service**.
3. Environment: **Python**.
4. **Build command**: `pip install -r requirements.txt`
5. **Start command**: `gunicorn wsgi:application`
6. After deploy, you get a public URL usable on any phone/laptop.

> Set environment variables (optional):
- `FLASK_SECRET` — your secret key for sessions.

## B) Deploy to Railway
1. Create new project → **Deploy from GitHub** (this folder).
2. Add a **Service** (Python).
3. **Start Command**: `gunicorn wsgi:application`
4. Set `PORT` env var only if Railway asks (Gunicorn uses `$PORT` automatically).

## C) Deploy to Heroku (if available)
```
heroku create
heroku buildpacks:add heroku/python
git push heroku main
heroku ps:scale web=1
heroku open
```

## D) Local Wi‑Fi sharing (same network)
```
pip install -r requirements.txt
python app.py
```
If you want others on your Wi‑Fi to access:
- Ensure `app.py` uses `host='0.0.0.0', port=5000` (it does).
- Find your PC IP (Windows: `ipconfig`, Mac/Linux: `ifconfig`).
- Open on phone: `http://<YOUR_PC_IP>:5000`

## Notes
- SQLite DB file (`data.db`) is created automatically on first run.
- To start fresh, delete `data.db` and restart.
- For production, consider moving to a managed Postgres later; SQLite is fine to begin with.
