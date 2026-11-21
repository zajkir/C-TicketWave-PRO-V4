# Ceyrl V5 · Personal Ticket Workspaces

A professional, private-by-design ticket and sales manager with a new responsive navy UI, real backend APIs and independent database/PDF storage for **every registered user**.

## What changed from V4

**V4 used one shared team database. V5 does not.** Every account has its own SQLite inventory database, its own encrypted PDF vault and its own records. No one can view another user's tickets, events, PDFs, listings, sales or expenses via the public UI/API. A Google account can now **register itself**, without a team invitation. Password-based signup requires email verification. Previous shared team roles have been removed from the application.

## Features

- Self-service registration through **Google** (verified OpenID Connect) or **email + password** (SMTP verification)
- Password login, forgotten-password email reset, link Google to an existing password account, profile editing, session logout and Argon2 hashing
- Server-controlled, per-user SQLite files: `data/users/<user_uuid>/inventory.sqlite3`
- Per-user Fernet-encrypted ticket PDFs: `data/users/<user_uuid>/vault/` and `.encryption_key`
- Independent events, ticket lots/seat locations, multi-PDF attachments, local listings, sales, expenses, CSV exports, audit history
- Atomic stock deductions when sales are recorded; prevents overselling
- Account-specific analytics, clear net-profit and ROI calculation for EUR, recent sales and a revenue trend visualization
- Fully reworked login, responsive dashboard, tables, filtering, modals, navigation, mobile layout and account management
- Includes API tests that prove **two different users cannot read each other's data**

## Local Windows run

1. Install Python 3.11 or newer.
2. Extract this project into a **new** folder; do not overwrite the existing V4 folder.
3. Double-click `start-windows.bat` and open http://127.0.0.1:8765.
4. Local developer mode permits email verification without an external SMTP server. This mode must NEVER be enabled on a public server.
5. Register two test accounts and confirm that each has its own inventory.

## Production deployment on Bot-Hosting.net

1. Create a new **Python Application** using this repository, branch `main`.
2. Startup: `python main.py`; install: `pip install -r requirements.txt`.
3. In **Environment / Secrets** configure:
   - `CTW_DATA_DIR=/home/container/data` **only after confirming this path is persistent through redeployments**
   - `CTW_PUBLIC_BASE_URL=https://YOUR-REAL-APP-DOMAIN`
   - `CTW_SECURE_COOKIES=1`
   - **Google signup:** `CTW_GOOGLE_CLIENT_ID`, `CTW_GOOGLE_CLIENT_SECRET`
   - **Email signup (optional):** `CTW_SMTP_HOST`, `CTW_SMTP_PORT`, `CTW_SMTP_TLS`, `CTW_SMTP_FROM`, `CTW_SMTP_USER`, `CTW_SMTP_PASSWORD`
4. In Google Cloud, configure a Web OAuth client. Add the exact **Authorized redirect URI**: `https://YOUR-REAL-APP-DOMAIN/api/auth/google/callback`. Use Google Auth Platform's Branding / Audience pages and configure Test Users if in Testing mode.
5. Under Bot-Hosting.net Domains, enable and check HTTPS. The website must be accessible with `https://`.
6. Ensure the hosting provider can make outbound HTTPS calls to Google OAuth. Restart the deployment.
7. Test Google registration with TWO new distinct Google accounts and verify they see different empty workspaces.
8. Backup **the entire `CTW_DATA_DIR`** to separate secure storage, including SQLite databases, vault files and `.encryption_key` files. Always stop the service or use an SQLite-consistent backup before copying live DB files.

**Important:** Google sign-in will only appear when OAuth config is valid. Email/password registration is disabled on public hosting unless SMTP is configured. One can work if the other is not available. The project does **not** ask for Gmail inbox or Gmail API access.

### Privacy and security model

- One global `identity.sqlite3` stores users, sessions and Google account links.
- Every user account is assigned a random 32-character ID and an **independent inventory.sqlite3** file.
- Inventory access uses **only the authenticated ID from the session cookie**. Request parameters never control data paths.
- PDF files are encrypted at rest using a different key per user. A user can download only PDFs in their own database.
- The system validates user writes with an HTTP-only session cookie and a CSRF token. Public deployments must use HTTPS and Secure cookies.
- Open registration is intentional. Production should include backups, quotas, abuse monitoring, rate limiting at the reverse proxy/WAF, email deliverability checks and a security audit prior to storing valuable third-party tickets.
- V5 is meant for one hosted service with many *separate personal workspaces*. It is not an invitation-based shared team system anymore.

### Migration from V4 (critical)

**Do not copy the V4 `data/ticketwave.sqlite3` directly into V5** — V4 contained multiple members' shared workspace data and its schema is different. V5 intentionally starts with new, empty private workspaces.

**No automatic migration of shared V4 data is performed**, to prevent accidentally assigning multiple people's tickets or PDF files to the wrong person. Keep a backup of the entire V4 data directory (including `vault/` and `.encryption_key`) in a safe location. If you want to import V4 ticket data, first choose one authorized owner and perform an owner-reviewed, offline migration. Do not put the V4 data directory in a public GitHub repository.

### Ticket platforms

The application stores **local listing drafts** and offers sales tracking. It does **not** automatically post to Viagogo or generate Ticketmaster registrations. Those integrations need approved API access and a separate supported implementation.

### Reboots, restarts and 24/7

Application code is safe to pull from GitHub, but the database is *not* stored there. For reliable uptime, the hosting plan must be active and its persistent volume must survive restarts and redeployments. Free plans may have renewal/uptime conditions; this code by itself does not guarantee 24/7 availability.

## Testing

```bash
python -m pip install -r requirements.txt
python -m pytest -q
node --check static/app.js
```

Private-data tests include registration, two account-specific databases, independently encrypted PDF files, CSRF protection, non-existence of cross-account ticket IDs and atomic sale stock controls.

**Test status:** Local backend integration tests pass. The UI was inspected with representative mock data, not real customer data. Live Google OAuth/SMTP and a complete public deployment cannot be tested without your authorized credentials and hosting domain.
