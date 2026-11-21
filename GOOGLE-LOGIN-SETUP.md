# Google sign-in for C TicketWave PRO V4

Google registration is **invitation-only**. This is deliberate: ticket PDFs, inventory, and sales are confidential. A Google account by itself does not grant access. Administrator approval is required for each new team member.

## Features

- Sign in with a linked Google account using the **Continue with Google** button.
- An administrator can invite a team member from **Team Members**; the invited person can click **Register with Google** and use the exact invited email address.
- Existing members can open **My Account → Connect Google account**. For security the Google account's verified email must match their existing TicketWave email.
- Existing email/password login continues to work.
- The Google link uses Google's immutable OpenID subject (not merely an email string), verified signature, issuer, audience and nonce.
- OAuth authorization code flow with PKCE, a one-time database state and an HTTP-only SameSite=Lax browser state cookie.
- No Google access token, refresh token, password or Gmail messages are stored. Only the Google account ID, email-at-link and timestamp are saved.

## Set up Google Cloud

1. Open https://console.cloud.google.com/ and create/select a Google Cloud project.
2. Open **Google Auth Platform** and configure its **Branding** and **Audience** pages. If the app is in testing, add the invited Google accounts as test users as required by Google.
3. Open **Google Auth Platform → Clients** and create an OAuth client of type **Web application**.
4. Set the **Authorized redirect URI** to your **exact** HTTPS hostname followed by:

   `/api/auth/google/callback`

   For example, if your deployed address is `https://tickets.example.com`, use `https://tickets.example.com/api/auth/google/callback`. Do not use this example hostname literally.
5. Copy the **Client ID** and **Client secret** from Google Cloud to the **Environment/Secrets** area in Bot-Hosting.net, not to GitHub.

## Bot-Hosting.net environment variables

| Variable | Value |
| --- | --- |
| `CTW_GOOGLE_CLIENT_ID` | Google Web OAuth Client ID |
| `CTW_GOOGLE_CLIENT_SECRET` | Google Web OAuth Client Secret |
| `CTW_PUBLIC_BASE_URL` | Exact public origin, e.g. `https://your-actual-domain.example` |
| `CTW_SECURE_COOKIES` | `1` (required for public HTTPS hosting) |
| `CTW_ALLOWED_ORIGINS` | Same public HTTPS origin |
| `CTW_DATA_DIR` | Provider-confirmed persistent data directory |

Restart your deployment after saving the environment variables. The login form will show the Google button only when the server has a valid configuration.

## Registration / login workflows

**First administrator**: Create the initial workspace with an email and strong password and the server-side bootstrap code. Google cannot silently create an administrator.

**New colleague**: Administrator creates an invitation for their email and grants the appropriate role. The colleague opens the invite link and chooses **Register with Google**. Google must verify the *same email*. The invitation is consumed once.

**Existing colleague**: Sign in normally, open **My Account**, choose **Connect Google account**, and approve the Google sign-in for the matching email. On future visits use **Continue with Google**.

**Someone without an invite**: Will **not** be registered or gain access through Google.

## Troubleshooting

- **No Google button**: Missing one or more Google OAuth environment variables, invalid public URL, or an initial workspace still needs setup.
- **redirect_uri_mismatch**: The Google Cloud callback must exactly equal `CTW_PUBLIC_BASE_URL + /api/auth/google/callback`, including HTTPS and hostname.
- **not-linked**: Sign in with password first and link the matching Google account, or ask an administrator for a Google-enabled invitation.
- **invite-email-mismatch**: The signed-in Google account must match the email on the invitation.
- **state / expired**: Try again in one browser tab within 10 minutes; ensure HTTPS cookies are allowed.
- **Google app is in testing**: The Google account may need to be added to the OAuth test-user allowlist in Google Cloud.
- **provider**: Verify the Client ID, secret, network egress from the host and Google OAuth consent configuration.

This feature requires outbound HTTPS connections to Google's OAuth servers and Google's token verification certificates. It has not been tested against a live Google OAuth client without credentials; do a real account test before inviting the full team.

Never post Client secrets, account passwords or PDF files in chat, code or public GitHub.
