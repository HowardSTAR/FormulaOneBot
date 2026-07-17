"""
Скрипт для запуска веб-сервера Mini App отдельно.
Использование: python run_web.py
"""
import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.api.miniapp_api:web_app",
        host="0.0.0.0",
        port=int(os.getenv("WEB_PORT", "8000")),
        reload=os.getenv("WEB_RELOAD", "false").lower() in {"1", "true", "yes"},
        proxy_headers=True,
        forwarded_allow_ips=os.getenv("FORWARDED_ALLOW_IPS", "127.0.0.1"),
    )
