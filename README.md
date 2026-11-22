# Ceyrl V6 · Personal Ticket Workspaces

A professional, private-by-design ticket and sales manager with a new responsive navy UI, real backend APIs and independent database/PDF storage for **every registered user**.

## Event Radar — working sources and global concert setup (2026-11-22)

**Why was Calin/BTS/Noah Kahan showing no matches?** The free third-party music services previously used by Ceyrl have become unreliable or inaccessible. A real, unauthenticated GitHub Actions probe on November 22, 2026 obtained: Gigora **HTTP 402**, StungEvents **HTTP 410**, and Ticket Fairy **HTTP 200**. Unit tests with mocked providers are not evidence that a live provider accepts requests. The unsupported music adapters have now been removed from application search and source attribution.

**What now works without any API key?** Ticket Fairy public listings, ConcertHub's Polish concert catalog and existing limited sports feeds. This is genuinely usable but **not a comprehensive worldwide concert database**, so a missing artist must not be interpreted as "no tour". Search results are only shown when a reachable provider returns a real record; the interface offers external Ticketmaster and Songkick search links when a provider's catalog does not contain the requested show.

No API key is asked from end users. When those free catalogs have no results, the Event Radar offers direct Ticketmaster, Songkick, Bandsintown and ConcertHub web searches. No one should interpret an empty result as proof that an artist has no concerts. Polish ConcertHub entries that supply only a day (not an exact timezone-aware start time) can be viewed at their source but are deliberately not automatically imported as timed Ceyrl events.

**For broad artist and Ticketmaster concert coverage:** The Ceyrl **operator** (not every user) creates one free Ticketmaster Developer API key at [Ticketmaster Developer Portal](https://developer.ticketmaster.com/) and adds the secret to the Bot-Hosting.net **Environment / Secrets** as `CTW_TICKETMASTER_API_KEY`. Restart the Ceyrl process. Logged-in users can then search Ticketmaster Discovery through the server; no one sees or needs their own key. Exact event results depend on Ticketmaster inventory, coverage, API access, rate limits and service status. <https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/>

When a shared key is configured, Ceyrl prioritizes it over any old personal key and checks Ticketmaster first, falling back to Ticket Fairy if there are no matches or the provider is unavailable. The response distinguishes "shared key missing" from "no catalog results" and reports provider errors rather than inventing show dates. The Event Radar UI shows an optional site-owner setup guide; quick artist buttons remain search shortcuts, **not concert announcements**.

Security: Credentials remain server-side, there are rate limits for search, the provider URL is fixed, and ticket/event import requires an authenticated action. Existing user databases, encrypted PDF vaults, original imports and audit history are preserved. Legacy Gigora/Stung/Tickets.dev API code was removed, not user data. Live connections must be checked again after deploying to the actual hosting environment.

---

## Event Radar: no personal API keys + security hardening (November 2026)

**Deployment:** Back up the entire persistent `CTW_DATA_DIR`, including `identity.sqlite3`, all `users/<uuid>/inventory.sqlite3` files, encrypted PDFs and each `.encryption_key`. Pull the latest `main`, restart the hosting process and refresh with Ctrl+F5. The site is expected to use HTTPS with `CTW_SECURE_COOKIES=1` and `CTW_PUBLIC_BASE_URL` set exactly to the public origin.

**Removed:** Magic Inbox is no longer registered, displayed, or bundled. Its email webhook, draft upload/approval endpoints, CSS/JS and Python integration have been removed. **Historic Magic Inbox tables and staged encrypted files are deliberately NOT erased** during this update: production user databases and private vaults stay untouched. Owners can later decide on data retention and migration. Remove obsolete `CTW_MAGIC_INBOX_DOMAIN` and `CTW_MAILGUN_WEBHOOK_SIGNING_KEY` from the hosting Environment if previously configured; revoke old mail routes and secrets separately in the provider dashboard. Incoming emails are no longer accepted by Ceyrl.

**Keyless Radar:** Open Event Radar and enter an artist, event or competition. The updated search offers **All events / Concerts & festivals / Sports & football** filters. Music and general events use the official [Ticket Fairy public events API](https://www.ticketfairy.com/developers), which only includes events in Ticket Fairy's catalog. Sports searches additionally check [TheSportsDB's documented limited public sports API](https://www.thesportsdb.com/documentation) and the publicly readable but **unofficial** ESPN scoreboard feeds for selected football leagues (including UEFA Nations League). This broader search is still not a comprehensive ticket/event database; ESPN and TheSportsDB schedules do not establish tickets are on sale. The user gets source labels, warnings for unavailable providers and an explicit link to [UEFA's official Nations League fixtures](https://www.uefa.com/uefanationsleague/fixtures-results/) when relevant. For other events the UI offers an external Ticketmaster search link rather than inventing event listings. Optionally, the server operator can set `CTW_TICKETMASTER_API_KEY` to use the Ticketmaster catalog; old encrypted personal keys remain stored for compatibility but users no longer see a key-entry UI. Ticketmaster itself requires authentication, so its full catalog cannot be offered anonymously without a server-side key. The backend only fetches fixed HTTPS provider URLs, never user-selected URLs, with no redirects. Public events are checked and normalized; event import is account-scoped and requires explicit action.

**Security changes:** Only the configured public origin is trusted for state-changing browser requests; spoofed Host headers no longer authorize an attacker-controlled Origin. Cross-site Fetch Metadata state-changing requests are rejected. Response headers now enforce `no-referrer`, a restrictive Content Security Policy, same-origin opener/resource policies, and restricted browser permissions. Authentication now rate-limits requests by client IP as well as email, protects password changes against repeated attempts and keeps at most five active sessions per account. Event Radar actions share a persistent provider quota across users. PDF downloads validate resolved vault paths and use properly sanitized filenames in HTTP headers.

**Limitations:** Public Radar providers do not guarantee comprehensive concert/festival or sports coverage; search results depend on third-party catalogs. TheSportsDB's free demonstration feed has limited results and rate limits. ESPN scoreboard endpoints are public but unofficial and may change without notice. For the 2026/27 Nations League, the UEFA competition calendar remains the authoritative source, and some future ties have no confirmed opponent, venue or time. Do not create tickets from unknown dates. Rate-limit enforcement is app-side and does not replace a reverse-proxy/WAF. Real internet provider availability, hosting HTTPS configuration, backups, restore drills and penetration testing still require production validation.

---

## GPT-5.4 mini Copilot – live AI integration

The Copilot can now use **real GPT-5.4 mini** via OpenAI's Responses API (model ID `gpt-5.4-mini`), instead of presenting keyword-based local replies as AI.

### Set up on Bot-Hosting.net

1. Back up your persistent `CTW_DATA_DIR` including each account's `.encryption_key`.
2. Create an OpenAI API project and key in [OpenAI Platform API Keys](https://platform.openai.com/api-keys). Set up separate API billing and a project-level spend/usage safeguard. ChatGPT subscriptions do not include API usage.
3. In your hosting service **Environment / Secrets** (never in the GitHub repo) set `CTW_OPENAI_API_KEY` to your key.
4. The model is fixed to `gpt-5.4-mini`, so older `CTW_OPENAI_MODEL` overrides are no longer used. Optional environment settings:
   - `CTW_OPENAI_WEB_SEARCH=1` (default) enables the built-in paid web search tool. To prohibit web search entirely use `0`. At most one web tool call is permitted per answer.
   - `CTW_OPENAI_MONTHLY_LIMIT_USD=5` (default) is an **estimated application-side global** API-usage guard. It is not a guaranteed billing cap; web pricing and token accounting can change. Also set a budget/alerts in OpenAI Platform.
   - `CTW_OPENAI_USER_DAILY_CALLS=30` (default) caps the number of attempts by each account each UTC day, with an additional limit of four calls per minute.
5. Restart the application, refresh the browser and open **AI Copilot**. Its connection banner reports whether a server key exists (not whether its permissions or billing have been verified). Ask a test question to verify actual provider connectivity.

### Privacy and functionality

- When **Use GPT-5.4 mini** is enabled, the app sends the user's question, the most recent encrypted chat turns (decrypted only in memory for that request), and numeric totals from the current user's own account. This includes counts, EUR revenue and recorded EUR fees, but does not include account emails, PDF content, secrets or attachment filenames.
- **Include ticket details** is a separate opt-in that also shares a *limited preview* of event names/dates/venues and ticket lot fields, so users can ask specific inventory questions. Event titles are treated as untrusted data, not instructions.
- **Web search** is an explicit toggle, enabled by default once the admin has configured GPT. When the model uses it, the response shows clickable citations to sources returned by the API. Search usage adds provider charges.
- The server uses `store=false`; no action changes ticket inventory or creates marketplace listings. The model is a read-only adviser, not an autonomous seller. Private chat messages are encrypted with the account's existing Fernet key and stored in its personal SQLite database. Users can delete their own chat history.
- The local helper remains available when the online switch is off, but clearly labels rule-based replies as **OFFLINE HELPER**. It does not pretend to know general facts or current information when live AI is not connected.
- Usage estimates are recorded in a small shared usage ledger for rate/budget monitoring; no conversation contents are stored there. User chat content remains isolated. Failed/unknown usage can be conservatively counted toward the estimated budget.

**Troubleshooting:** `503` often means no API key, invalid API credentials or insufficient model access. `429` means rate/estimated budget/provider quota was exceeded. `502`/ `504` can indicate provider errors or networking timeouts. The app never prints the secret to a browser response. Live API calls require your account's own credentials and are not made by automated tests.

---

## Ceyrl X – modules 1, 3, 5 and 6 (November 2026)

This release adds four functional, authenticated modules on top of Ceyrl V6, without changing existing account IDs, event IDs or the V5 database structure. Each new feature creates its own additive tables in the **currently logged-in user's** private SQLite database, only as needed.

**1. AI Copilot:** A private, read-only assistant that can summarize local counts offline or use the fixed GPT-5.4 mini model via `CTW_OPENAI_API_KEY` in the server Environment. Online chat shares recent messages and account aggregates, with optional explicitly enabled web search and limited ticket details. It never sends PDF bytes, account credentials or attachment filenames; the server uses `store=false`. GPT requests are subject to estimated usage limits. Real provider errors are shown instead of disguised as AI-generated replies.

**3. Double-Sale Shield:** Automatically refuses new ticket lots when exactly parsed seat numbers overlap an existing lot in the same event, section and row. Supports explicit seats like `2,3`, `4-7` and `A1-A3`. Uncertain freeform seats and general admission are intentionally not treated as a provable conflict. Existing duplicate seats and multiple locally active listings are reported by the Shield page. Recording a sale immediately **pauses all local ready/listed records** for that ticket lot, even when some seats remain, so the owner can review quantities. Repeat channel + order reference values are blocked. **External marketplace listings are not modified**; users must update them separately. This does not guarantee no double-sale across external platforms.

**5. Event Radar:** Public searches work with no user key via Ticket Fairy and selected sports feeds. For global artist searches the site operator may set one shared Ticketmaster Discovery API key; users still never need individual keys. Results are labeled by provider and only real returned event records can be imported. A configured legacy personal or shared `CTW_TICKETMASTER_API_KEY` can still provide Ticketmaster Discovery API results. Search results clearly identify their source and **do not claim to cover every event**; Ticket Fairy's catalog is not a complete Ticketmaster database. Users may follow searches privately, refresh watches manually, and explicitly import source-identified events into their personal calendar. Keyless event imports can use only results obtained through the authenticated user's own recent search/watch refresh (30-minute scoped cache); unverified IDs are rejected. Provider errors and rate limits are surfaced. No marketplace listings are changed and there is no automatic event monitoring.

**6. Delivery Readiness:** A per-ticket checklist of event date, seat details, format, transfer/possession confirmation, provider restrictions, and availability. Each user can update delivery details; the system computes a 0–100 completeness score. For PDF delivery, an actual attached PDF contributes to readiness. For mobile transfer, the owner confirms transfer availability. The score **does not validate authenticity** or guarantee venue acceptance or successful delivery. It is advisory only.

**Privacy and deployment:** All endpoints require the logged-in user. Writes and charge-triggering AI calls require CSRF. New SQLite tables are account-scoped, created additively and safely; old account files remain in place. Back up `CTW_DATA_DIR` (especially `identity.sqlite3`, each user's `inventory.sqlite3`, `vault/` and `.encryption_key`) before updating. Restart Bot-Hosting.net after pulling `main`; reload with Ctrl+F5. Use **AI Copilot**, **Double-Sale Shield**, **Event Radar** and **Delivery Readiness** from the left sidebar.

**Testing:** `python -m pytest -q` includes account-isolation regression tests for all four modules. GitHub Actions also checks frontend syntax. Live OpenAI, optional Ticketmaster and public Ticket Fairy API connectivity require actual provider availability and are not exercised by mocked CI tests.

---

## Ceyrl V6 – Premium Operations Upgrade (November 2026)

This is a **working feature upgrade**, not a mockup. The existing V5 login, Google OAuth flow, per-user SQLite inventories and PDF encryption remain intact. V6 adds these verified source changes:

- **Action Center** in the sidebar: operational alerts for upcoming events (within 7 days), ticket lots without attached PDFs (mobile-transfer tickets may not require PDFs), local draft listings and an onboarding action when no events exist.
- **7 / 30 / 90 day Sales Intelligence** with current vs previous period metrics. These figures are based only on the authenticated user's sales.
- **EUR financial clarity**: the V6 window **sales margin** is EUR revenue minus EUR marketplace fees minus purchase cost of sold tickets. Event expenses and non-EUR values are **excluded** from this period-specific margin. The existing Analytics/Recaps section remains the place for event-level profit including associated EUR expenses.
- **Universal private search**: use the search button or Ctrl+K / ⌘K to search your own events, ticket lots, seat details and local listings. No external provider search, no access to other users' databases.
- **Premium UI**: new responsive V6 stylesheet, richer typography, action dashboard, quick actions, dark indigo surfaces with violet/emerald/gold accents, keyboard-search dialog and existing optional ambient motion.
- **Accessibility**: keyboard-operated search, semantic labels, motion pause and reduced-motion support.
- **Regression tests**: `tests/test_v5.py`, `tests/test_v6.py`; GitHub Actions `Ceyrl application checks` runs Python tests and JavaScript syntax checks on each commit.

**Update safely on Bot-Hosting.net:** Back up the entire persistent `CTW_DATA_DIR` before restarting (including `identity.sqlite3`, per-user SQLite databases, PDF vaults, and their encryption keys). Pull the latest `main` and restart the deployment; refresh the browser with Ctrl+F5. This V6 release **does not change the database schema** or add required environment variables. Keep `CTW_PUBLIC_BASE_URL`, HTTPS cookies, Google OAuth settings and SMTP settings as configured.

**Limitations:** Automatic listing to Viagogo and external event imports are **not** activated in this release. V6 operational alerts are computed when the user opens the page; they do not run as scheduled notifications. For public hosting, backups, monitoring, SMTP deliverability and production security hardening remain essential.

---

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


## Ceyrl visual atmosphere (new)

The real web frontend now includes an animated, noninteractive background with floating ticket outlines, subtle € symbols, ambient violet / teal lighting, and soft drifting particles. Its CSS is in `static/ambient.css`. Motion can be paused using the **Motion on / Motion off** button in the top bar; that preference is stored locally in each browser, not in the user database. The UI respects `prefers-reduced-motion` and disables animation when reduced motion is requested by the device.

These changes affect only presentation. They do **not** alter account separation, backend routes, data storage, authentication, Google OAuth, or encrypted PDF records. After pulling the latest GitHub revision on Bot-Hosting.net, restart the deployment and refresh the page (Ctrl+F5) to load the latest assets.
