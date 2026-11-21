# C TicketWave V5 · Bot-Hosting.net Quick Deploy

1. GitHub repo `zajkir/C-TicketWave-PRO-V4` (the repository name remains V4 for continuity; code version is **V5**), branch `main`.
2. New **Application → Python** deployment.
3. Entrypoint: `main.py`, command: `python main.py`. Install dependencies `pip install -r requirements.txt`.
4. Set `CTW_DATA_DIR=/home/container/data` after checking this is *persistent across restart/redeploy*. The application creates `identity.sqlite3` and the `users/` folder inside it.
5. Set `CTW_PUBLIC_BASE_URL=https://ACTUAL-PUBLIC-DOMAIN` and `CTW_SECURE_COOKIES=1`.
6. For **Google signup**, create a Google Cloud Web OAuth client, add callback `https://ACTUAL-PUBLIC-DOMAIN/api/auth/google/callback`, then set secret variables `CTW_GOOGLE_CLIENT_ID` and `CTW_GOOGLE_CLIENT_SECRET`.
7. For **email/password signup**, set SMTP variables (`CTW_SMTP_HOST`, `CTW_SMTP_PORT`, `CTW_SMTP_TLS`, `CTW_SMTP_FROM`, `CTW_SMTP_USER`, `CTW_SMTP_PASSWORD`) — these are required for production email verification and resets.
8. Set up HTTPS domain, restart and test `/health`. Ensure `Google` login appears once OAuth is configured.
9. Register Account A and Account B. Create an event, tickets and a PDF in Account A. Verify Account B sees **no records**.
10. Configure reliable offsite backups of **all of CTW_DATA_DIR**, including hidden encryption keys.

Never use `CTW_LOCAL_DEV_TOKENS=1` on a public deployment.

**Migration:** The V4 workspace database is shared and must NOT be copied directly to V5. V5 creates empty, isolated personal workspaces. Preserve any old files in a separate secure backup; migrate only with explicit per-ticket ownership review.
