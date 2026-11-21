"""Bot-Hosting.net / generic Python deployment entrypoint."""
import os
import uvicorn

if __name__ == '__main__':
    port=int(os.environ.get('SERVER_PORT') or os.environ.get('PORT') or '8765')
    uvicorn.run('app:app',host='0.0.0.0',port=port,workers=1,proxy_headers=True)
