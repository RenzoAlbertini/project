"""Response composition for multi-intent assistant outputs."""

from __future__ import annotations

from collections.abc import Callable

from core.router import RouteDecision


DecisionRunner = Callable[[RouteDecision], str]


def order_decisions(decisions: list[RouteDecision]) -> list[RouteDecision]:
    """Return decisions in the order used to build one unified answer."""
    priority = {
        "tutor": 0,
        "career_advisor": 0,
        "web_search": 0,
        "exam_start": 1,
        "exam_answer": 1,
        "exam_next": 1,
        "study_planner": 2,
    }
    return sorted(decisions, key=lambda decision: priority.get(decision.mode, 0))


def compose_unified_response(
    decisions: list[RouteDecision],
    run_decision: DecisionRunner,
) -> str:
    """Execute routed capabilities and merge their outputs into one answer."""
    explanation_parts: list[str] = []
    exam_part = ""
    study_part = ""

    for decision in order_decisions(decisions):
        result = run_decision(decision)
        if decision.mode in {"tutor", "career_advisor", "web_search"}:
            explanation_parts.append(result)
        elif decision.mode in {"exam_start", "exam_answer", "exam_next"}:
            exam_part = result
        elif decision.mode == "study_planner":
            study_part = result

    sections: list[str] = []
    if explanation_parts:
        sections.append("### Explanation\n\n" + "\n\n".join(explanation_parts).strip())
    if exam_part:
        sections.append("### Exam Question\n\n" + exam_part.strip())
    if study_part:
        sections.append("### Study Plan\n\n" + study_part.strip())

    return "\n\n".join(sections)
