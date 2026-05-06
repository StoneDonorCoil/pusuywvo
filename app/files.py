"""
Модуль для работы с файлами — загрузка, хранение, отправка.
Поддерживает любые форматы: фото, музыка, zip, документы и т.д.
"""

import os
import uuid
from pathlib import Path

from fastapi import UploadFile

UPLOADS_DIR = Path(__file__).parent.parent / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 МБ


def get_safe_filename(original: str) -> str:
    """Генерирует безопасное имя файла, сохраняя расширение."""
    ext = Path(original).suffix
    unique_id = uuid.uuid4().hex[:8]
    safe_name = "".join(c for c in Path(original).stem if c.isalnum() or c in "-_.")
    return f"{safe_name}_{unique_id}{ext}"


async def save_upload(file: UploadFile) -> dict:
    """Сохраняет загруженный файл и возвращает метаданные."""
    filename = get_safe_filename(file.filename or "file")
    filepath = UPLOADS_DIR / filename

    content = await file.read()
    file_size = len(content)

    if file_size > MAX_FILE_SIZE:
        raise ValueError(f"Файл слишком большой: {file_size} байт (макс {MAX_FILE_SIZE})")

    filepath.write_bytes(content)

    return {
        "id": filename,
        "original_name": file.filename,
        "saved_name": filename,
        "size": file_size,
        "content_type": file.content_type or "application/octet-stream",
        "path": str(filepath),
    }


def list_uploads() -> list[dict]:
    """Список всех загруженных файлов."""
    files = []
    for f in sorted(UPLOADS_DIR.iterdir()):
        if f.is_file():
            files.append({
                "id": f.name,
                "name": f.name,
                "size": f.stat().st_size,
            })
    return files


def get_file_path(file_id: str) -> Path | None:
    """Получает путь к файлу по ID."""
    filepath = UPLOADS_DIR / file_id
    if filepath.exists() and filepath.is_file():
        return filepath
    return None


def delete_file(file_id: str) -> bool:
    """Удаляет файл."""
    filepath = UPLOADS_DIR / file_id
    if filepath.exists() and filepath.is_file():
        filepath.unlink()
        return True
    return False
