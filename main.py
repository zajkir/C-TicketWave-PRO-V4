"""Entrypoint for Python app hosting platforms (including Bot-Hosting)."""
import os
import sys
import uvicorn


def main() -> None:
    port_text = os.getenv("SERVER_PORT") or os.getenv("PORT") or os.getenv("CTW_PORT") or "8765"
    try:
        port = int(port_text)
        if not 1 <= port <= 65535:
            raise ValueError("Invalid port")
    except ValueError:
        sys.exit("SERVER_PORT/PORT must be a valid TCP port number.")
    if os.getenv("CTW_SECURE_COOKIES") != "1":
        print("WARNING: Secure cookies disabled. Enable CTW_SECURE_COOKIES=1 when serving over HTTPS.", flush=True)
    uvicorn.run("app:app", host="0.0.0.0", port=port, workers=1, proxy_headers=True)


if __name__ == "__main__":
    main()
