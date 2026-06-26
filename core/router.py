"""Intent routing for the unified university assistant chat."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RouteDecision:
    mode: str
    topic: str
    difficulty: str = "Intermediate"
    duration_weeks: int = 4
    source_count: int = 5
    reason: str = ""


def route_user_input(message: str, awaiting_exam_answer: bool = False) -> RouteDecision:
    """Classify a free-text user message into one assistant capability."""
    return route_user_inputs(message, awaiting_exam_answer=awaiting_exam_answer)[0]


def route_user_inputs(message: str, awaiting_exam_answer: bool = False) -> list[RouteDecision]:
    """Classify a free-text user message into one or more assistant capabilities."""
    text = message.strip()
    lowered = text.lower()

    if awaiting_exam_answer and not _has_any(lowered, _OVERRIDE_KEYWORDS):
        return [
            RouteDecision(
                mode="exam_answer",
                topic="current exam question",
                reason="An exam question is waiting for an answer.",
            )
        ]

    if _has_any(lowered, _EXAM_NEXT_KEYWORDS):
        return [
            RouteDecision(
                mode="exam_next",
                topic=_extract_topic(text) or "current exam topic",
                reason="The request asks to continue the exam.",
            )
        ]

    decisions: list[RouteDecision] = []
    topic = _extract_topic(text) or _extract_shared_topic(text)

    if _has_any(lowered, _EXPLANATION_KEYWORDS):
        decisions.append(
            RouteDecision(
                mode="tutor",
                topic=topic or text,
                reason="The request asks for an explanation or tutoring.",
            )
        )

    if _has_any(lowered, _EXAM_KEYWORDS):
        decisions.append(
            RouteDecision(
                mode="exam_start",
                topic=topic or _remove_keywords(text, _EXAM_KEYWORDS) or "the requested topic",
                difficulty=_extract_difficulty(lowered),
                reason="The request asks for exam practice or a quiz.",
            )
        )

    if _has_any(lowered, _STUDY_PLAN_KEYWORDS):
        decisions.append(
            RouteDecision(
                mode="study_planner",
                topic=topic or _remove_keywords(text, _STUDY_PLAN_KEYWORDS) or "the requested topic",
                difficulty=_extract_difficulty(lowered),
                duration_weeks=_extract_duration_weeks(lowered),
                reason="The request asks for preparation or a structured study plan.",
            )
        )

    if _has_any(lowered, _CAREER_KEYWORDS):
        decisions.append(
            RouteDecision(
                mode="career_advisor",
                topic=topic or text,
                reason="The request asks for job, CV, skills, projects, or career guidance.",
            )
        )

    if _has_any(lowered, _WEB_KEYWORDS):
        decisions.append(
            RouteDecision(
                mode="web_search",
                topic=topic or text,
                source_count=_extract_source_count(lowered),
                reason="The request asks for current information or sources.",
            )
        )

    if decisions:
        return decisions

    return [
        RouteDecision(
            mode="tutor",
            topic=topic or text,
            reason="Default tutoring conversation.",
        )
    ]


def mode_label(mode: str) -> str:
    return {
        "study_planner": "Study Planner",
        "exam_start": "Exam Simulator",
        "exam_answer": "Exam Simulator",
        "exam_next": "Exam Simulator",
        "tutor": "Tutor",
        "web_search": "Web Search",
        "career_advisor": "Career Advisor",
    }.get(mode, "Tutor")


_WEB_KEYWORDS = {
    "search",
    "web",
    "online",
    "source",
    "sources",
    "latest",
    "current",
    "today",
    "news",
    "look up",
    "cerca",
    "cercami",
    "trova",
    "fonti",
    "fonte",
    "aggiornato",
    "aggiornata",
    "internet",
}

_EXPLANATION_KEYWORDS = {
    "explain",
    "explanation",
    "teach",
    "describe",
    "what is",
    "how does",
    "spiegami",
    "spiega",
    "insegnami",
    "cos'è",
    "cosa è",
    "come funziona",
}

_EXAM_KEYWORDS = {
    "exam",
    "quiz",
    "test me",
    "ask me",
    "question",
    "simulate",
    "simulator",
    "esame",
    "quiz",
    "interrogami",
    "fammi una domanda",
    "simula",
    "valuta la mia risposta",
}

_EXAM_NEXT_KEYWORDS = {
    "next question",
    "another question",
    "continue exam",
    "prossima domanda",
    "altra domanda",
    "continua esame",
}

_CAREER_KEYWORDS = {
    "career",
    "job",
    "role",
    "interview",
    "portfolio",
    "project ideas",
    "skills",
    "cv",
    "resume",
    "carriera",
    "lavoro",
    "ruolo",
    "colloquio",
    "progetti",
    "competenze",
}

_STUDY_PLAN_KEYWORDS = {
    "study plan",
    "learning plan",
    "roadmap",
    "schedule",
    "prepare",
    "preparation",
    "prep",
    "learn",
    "study",
    "planner",
    "piano di studio",
    "preparare",
    "preparazione",
    "programma",
    "roadmap",
    "imparare",
    "studiare",
}

_OVERRIDE_KEYWORDS = (
    _WEB_KEYWORDS
    | _EXPLANATION_KEYWORDS
    | _EXAM_NEXT_KEYWORDS
    | _EXAM_KEYWORDS
    | _CAREER_KEYWORDS
    | _STUDY_PLAN_KEYWORDS
)


def _has_any(text: str, keywords: set[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _extract_difficulty(text: str) -> str:
    if any(word in text for word in ["advanced", "difficile", "avanzato", "expert"]):
        return "Advanced"
    if any(word in text for word in ["beginner", "basic", "facile", "base", "principiante"]):
        return "Beginner"
    return "Intermediate"


def _extract_duration_weeks(text: str) -> int:
    match = re.search(r"(\d{1,2})\s*(?:week|weeks|settimana|settimane)", text)
    if not match:
        return 4
    return max(1, min(int(match.group(1)), 16))


def _extract_source_count(text: str) -> int:
    match = re.search(r"(\d{1,2})\s*(?:sources|fonti|links|link)", text)
    if not match:
        return 5
    return max(1, min(int(match.group(1)), 8))


def _extract_topic(text: str) -> str:
    patterns = [
        r"\b(?:for|about|on|su|per|riguardo|about)\s+(.+)$",
        r"\b(?:learn|study|imparare|studiare)\s+(.+)$",
        r"\b(?:as|come)\s+(?:a|an|un|una)?\s*(.+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return _clean_topic(match.group(1))
    return ""


def _extract_shared_topic(text: str) -> str:
    cleaned = _remove_keywords(text, _OVERRIDE_KEYWORDS)
    cleaned = re.sub(r"\b(?:and|also|then|plus|e|anche|poi|inoltre|with|con|for|per|about|su)\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return _clean_topic(cleaned)


def _remove_keywords(text: str, keywords: set[str]) -> str:
    cleaned = text
    for keyword in sorted(keywords, key=len, reverse=True):
        cleaned = re.sub(re.escape(keyword), "", cleaned, flags=re.IGNORECASE)
    return _clean_topic(cleaned)


def _clean_topic(topic: str) -> str:
    cleaned = re.sub(r"\b(?:beginner|intermediate|advanced|base|principiante|avanzato)\b", "", topic, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b\d{1,2}\s*(?:week|weeks|settimana|settimane|sources|fonti)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" .,:;-")
