"""
Модуль для работы с базой знаний бота.
Загружает текстовые файлы из папки knowledge/ и использует их как контекст.
"""

import os
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"


def load_knowledge() -> str:
    """Загружает все файлы из папки knowledge/ и возвращает как единый текст."""
    if not KNOWLEDGE_DIR.exists():
        return ""

    texts = []
    for file_path in sorted(KNOWLEDGE_DIR.glob("*.txt")):
        content = file_path.read_text(encoding="utf-8").strip()
        if content:
            texts.append(f"--- {file_path.name} ---\n{content}")

    return "\n\n".join(texts)


def get_system_prompt() -> str:
    """Читает системный промпт из файла system_prompt.txt."""
    prompt_file = KNOWLEDGE_DIR / "system_prompt.txt"
    if prompt_file.exists():
        return prompt_file.read_text(encoding="utf-8").strip()
    return "Ты — полезный AI-ассистент. Отвечай на русском языке. Будь дружелюбным и помогай пользователю."


def build_system_message() -> str:
    """Собирает финальный системный промпт с базой знаний."""
    base_prompt = get_system_prompt()
    knowledge = load_knowledge()

    if knowledge:
        return f"{base_prompt}\n\n--- БАЗА ЗНАНИЙ ---\nИспользуй следующую информацию при ответах:\n\n{knowledge}"

    return base_prompt
