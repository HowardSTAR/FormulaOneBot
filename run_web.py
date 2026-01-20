"""
Скрипт для запуска веб-сервера Mini App отдельно.
Использование: python run_web.py
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.api.miniapp_api:web_app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # для разработки
    )
