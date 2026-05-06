"""
Главный модуль приложения — FastAPI сервер для AI-бота.
"""

from fastapi import FastAPI, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import settings
from app.files import delete_file, get_file_path, list_uploads, save_upload
from app.knowledge import build_system_message
from app.ollama_client import chat_stream, check_health, list_models

app = FastAPI(title=settings.app_title)

app.mount("/static", StaticFiles(directory="static"), name="static")


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    model: str | None = None


@app.get("/", response_class=HTMLResponse)
async def index():
    """Главная страница — чат-интерфейс."""
    with open("static/index.html", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.post("/api/chat")
async def api_chat(request: ChatRequest):
    """Стриминг ответа от AI модели."""
    system_message = build_system_message()
    messages = [{"role": "system", "content": system_message}]
    messages.extend({"role": m.role, "content": m.content} for m in request.messages)

    async def generate():
        async for chunk in chat_stream(messages, model=request.model):
            yield chunk

    return StreamingResponse(generate(), media_type="text/plain")


@app.get("/api/models")
async def api_models():
    """Список доступных моделей."""
    models = await list_models()
    return {"models": models, "current": settings.model_name}


@app.get("/api/health")
async def api_health():
    """Проверка здоровья сервиса."""
    ollama_ok = await check_health()
    return {
        "status": "ok" if ollama_ok else "ollama_unavailable",
        "ollama": ollama_ok,
        "model": settings.model_name,
    }


@app.get("/api/config")
async def api_config():
    """Текущая конфигурация бота (публичная часть)."""
    return {
        "title": settings.app_title,
        "model": settings.model_name,
    }


# === Файловые эндпоинты ===


@app.post("/api/upload")
async def api_upload(file: UploadFile):
    """Загрузка файла (любой формат: фото, музыка, zip, документы и т.д.)."""
    try:
        result = await save_upload(file)
        return {"status": "ok", "file": result}
    except ValueError as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/files")
async def api_files():
    """Список загруженных файлов."""
    return {"files": list_uploads()}


@app.get("/api/files/{file_id}")
async def api_download(file_id: str):
    """Скачивание файла."""
    filepath = get_file_path(file_id)
    if filepath is None:
        return {"status": "error", "message": "Файл не найден"}
    return FileResponse(filepath, filename=filepath.name)


@app.delete("/api/files/{file_id}")
async def api_delete_file(file_id: str):
    """Удаление файла."""
    if delete_file(file_id):
        return {"status": "ok"}
    return {"status": "error", "message": "Файл не найден"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.app_host, port=settings.app_port)
