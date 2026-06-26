"""Prompt builders for university assistant workflows."""

from __future__ import annotations


def build_study_plan_prompt(
    topic: str,
    difficulty: str,
    duration_weeks: int,
    include_checks: bool,
) -> str:
    prompt = (
        f"Create a {difficulty.lower()} study plan for {topic}. "
        f"Duration: {duration_weeks} weeks. "
        "Use a simple weekly structure with goals, learning tasks, practice work, "
        "and one small project or deliverable."
    )
    if include_checks:
        prompt += " Include checkpoints and short self-assessment questions."
    return prompt


def build_exam_question_prompt(
    topic: str,
    difficulty: str,
    question_number: int,
    total_questions: int,
    previous_questions: list[str],
) -> str:
    prior = "\n".join(f"- {question}" for question in previous_questions) or "- None"
    return (
        f"Create exam question {question_number} of {total_questions} for {topic}. "
        f"Difficulty: {difficulty}. Ask exactly one question. "
        "Do not include the answer. Avoid repeating these previous questions:\n"
        f"{prior}"
    )


def build_exam_evaluation_prompt(
    topic: str,
    question: str,
    answer: str,
) -> str:
    return (
        "Evaluate this exam answer as a university tutor.\n"
        f"Topic: {topic}\n"
        f"Question: {question}\n"
        f"Student answer: {answer}\n\n"
        "Return exactly these sections:\n"
        "Score: X/10\n"
        "Feedback: concise feedback on correctness and missing ideas.\n"
        "Weak topics: comma-separated topics to review, or None.\n"
        "Model answer: a concise ideal answer."
    )


def build_tutor_prompt(message: str, weak_topics: list[str]) -> str:
    weak_topic_text = ", ".join(weak_topics) if weak_topics else "None recorded"
    return (
        "Act as a helpful university tutor. Explain clearly, ask one useful follow-up "
        "question when it helps, and adapt to the student's weak topics.\n"
        f"Weak topics: {weak_topic_text}\n"
        f"Student message: {message}"
    )


def build_career_prompt(
    target_role: str,
    current_skills: str,
    interests: str,
    weak_topics: list[str],
) -> str:
    weak_topic_text = ", ".join(weak_topics) if weak_topics else "None recorded"
    return (
        "Act as a practical career advisor for a university student or early-career technologist.\n"
        f"Target role: {target_role}\n"
        f"Current skills: {current_skills or 'Not specified'}\n"
        f"Interests: {interests or 'Not specified'}\n"
        f"Weak topics from study memory: {weak_topic_text}\n\n"
        "Suggest:\n"
        "1. Skills to build next.\n"
        "2. Three portfolio project ideas.\n"
        "3. A short 4-week action plan.\n"
        "4. Interview or certification preparation tips."
    )

