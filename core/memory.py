"""Lightweight JSON memory for study progress."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from config.settings import DATA_DIR


MEMORY_PATH = DATA_DIR / "student_memory.json"

def load_memory() -> dict[str, Any]:
    if not MEMORY_PATH.exists():
        return _default_memory()

    try:
        data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _default_memory()

    memory = _default_memory()
    for key, value in data.items():
        if key in memory:
            memory[key] = value
    return memory


def save_memory(memory: dict[str, Any]) -> None:
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_PATH.write_text(
        json.dumps(memory, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )


def remember_weak_topics(topics: list[str]) -> dict[str, Any]:
    memory = load_memory()
    existing = {topic.lower(): topic for topic in memory.get("weak_topics", [])}
    for topic in topics:
        cleaned = topic.strip()
        if cleaned and cleaned.lower() != "none":
            existing.setdefault(cleaned.lower(), cleaned)
    memory["weak_topics"] = sorted(existing.values(), key=str.lower)
    save_memory(memory)
    return memory


def remember_study_plan(topic: str, difficulty: str, duration_weeks: int) -> dict[str, Any]:
    memory = load_memory()
    memory.setdefault("study_plans", []).append(
        {
            "topic": topic,
            "difficulty": difficulty,
            "duration_weeks": duration_weeks,
            "created_at": _now(),
        }
    )
    save_memory(memory)
    return memory


def remember_exam_result(
    topic: str,
    score: float | None,
    feedback: str,
    weak_topics: list[str],
) -> dict[str, Any]:
    memory = remember_weak_topics(weak_topics) if weak_topics else load_memory()
    memory.setdefault("exam_results", []).append(
        {
            "topic": topic,
            "score": score,
            "feedback": feedback[:500],
            "weak_topics": weak_topics,
            "created_at": _now(),
        }
    )
    save_memory(memory)
    return memory


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_memory() -> dict[str, Any]:
    return {
        "weak_topics": [],
        "study_plans": [],
        "exam_results": [],
    }
