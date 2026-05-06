"""
Клиент для взаимодействия с Ollama API.
Поддерживает как потоковую передачу (streaming), так и обычные запросы.
"""

from collections.abc import AsyncGenerator

import httpx

from app.config import settings


async def chat_stream(
    messages: list[dict[str, str]],
    model: str | None = None,
) -> AsyncGenerator[str, None]:
    """Отправляет запрос к Ollama и стримит ответ по частям."""
    model = model or settings.model_name
    url = f"{settings.ollama_base_url}/api/chat"

    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("POST", url, json=payload) as response:
            response.raise_for_status()
            import json

            async for line in response.aiter_lines():
                if line.strip():
                    data = json.loads(line)
                    if "message" in data and "content" in data["message"]:
                        yield data["message"]["content"]
                    if data.get("done", False):
                        break


async def chat(
    messages: list[dict[str, str]],
    model: str | None = None,
) -> str:
    """Отправляет запрос к Ollama и возвращает полный ответ."""
    model = model or settings.model_name
    url = f"{settings.ollama_base_url}/api/chat"

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        return data["message"]["content"]


async def list_models() -> list[str]:
    """Получает список доступных моделей из Ollama."""
    url = f"{settings.ollama_base_url}/api/tags"

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            return [m["name"] for m in data.get("models", [])]
        except (httpx.HTTPError, KeyError):
            return []


async def check_health() -> bool:
    """Проверяет доступность Ollama."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(settings.ollama_base_url)
            return response.status_code == 200
    except httpx.HTTPError:
        return False
