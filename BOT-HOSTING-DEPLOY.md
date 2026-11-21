# Deploying C TicketWave PRO V4 on Bot-Hosting.net

This repository contains the FastAPI backend, static frontend, tests, and the Python hosting entrypoint `main.py`.

## Deployment steps

1. On Bot-Hosting.net create a separate **Application** deployment (not a Database deployment).
2. Select the GitHub repository `zajkir/C-TicketWave-PRO-V4`, branch `main`.
3. Select **Python** runtime.
4. Install dependencies with `pip install -r requirements.txt` if the provider does not install them automatically.
5. Select startup file `main.py` or startup command `python main.py`.
6. Configure Environment / Secrets using your own values:
   - `CTW_BOOTSTRAP_CODE`: strong random bootstrap code (required to create the first admin over the internet)
   - `CTW_SECURE_COOKIES=1`: mandatory for HTTPS browser sessions
   - `CTW_ALLOWED_ORIGINS=https://YOUR-APP-DOMAIN`: exact HTTPS domain of the app
   - `CTW_PUBLIC_BASE_URL=https://YOUR-APP-DOMAIN`: public app URL
   - `CTW_DATA_DIR=/home/container/data` or a **confirmed persistent directory** assigned by the provider
   - `CTW_ENABLE_LEGACY_WATCHLIST=0`
7. Create/attach an HTTPS domain and start the deployment.
8. Open `https://YOUR-APP-DOMAIN/health` to check the backend.
9. Open the app home page and create the initial administrator with the bootstrap code. Invite team members through the built-in interface.

**Never place passwords, encryption keys, live databases or customer PDFs in GitHub or the deployment source.**

## Persistence matters

The app uses SQLite and stores the database, the PDF vault and the encryption key under `CTW_DATA_DIR`. This directory **must survive restarts and redeploys**. Confirm the provider's persistence behavior before any real ticket data is uploaded. Back up **the entire directory**, including hidden files such as `.encryption_key`, to a separate secure location.

Without persistence, your data and stored PDFs may be lost on a redeploy. A free deployment may also require periodic renewal and therefore must not be assumed to run uninterrupted 24/7.

## Runtime

`main.py` listens on `0.0.0.0` and reads `SERVER_PORT`, `PORT`, or `CTW_PORT`; falls back to port 8765. Use only one worker with SQLite.

Health endpoint: `GET /health` → `{"status":"ok"}`.

## Public deployment security

Do not use plain HTTP to log in. Use the provider's TLS termination / HTTPS domain. Enable secure cookies and origin restrictions above. The app is designed for a single trusted team, not multi-tenant SaaS without additional security work. Keep user and document backups offsite.

Ticketmaster or Viagogo listing publication is not required for the inventory app to function. The V4 interface deliberately does not expose the older Find Events / Integrations / Event Watchlist pages, and it does not automatically post to Viagogo.
