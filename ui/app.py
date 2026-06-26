"""Unified Streamlit chat UI for the AI Personal University Assistant."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

import requests
import streamlit as st
from dotenv import load_dotenv

from core.memory import (
    load_memory,
    remember_exam_result,
    remember_study_plan,
)
from core.prompts import (
    build_career_prompt,
    build_exam_evaluation_prompt,
    build_exam_question_prompt,
    build_study_plan_prompt,
    build_tutor_prompt,
)
from core.router import RouteDecision, route_user_inputs
from tools.web_search import search_web_with_foundry

load_dotenv()


REQUEST_TIMEOUT_SECONDS = 180


@dataclass(frozen=True)
class Service:
    name: str
    port: str
    health_path: str = "/health"

    @property
    def url(self) -> str:
        server_url = os.getenv("SERVER_URL", "127.0.0.1")
        return f"http://{server_url}:{self.port}"

    @property
    def health_url(self) -> str:
        return f"{self.url}{self.health_path}"


def get_services() -> list[Service]:
    return [
        Service("University assistant", os.getenv("TITLE_AGENT_PORT", "10007")),
        Service("Outline agent", os.getenv("OUTLINE_AGENT_PORT", "10008")),
        Service("Routing agent", os.getenv("ROUTING_AGENT_PORT", "10009")),
    ]


def check_service(service: Service) -> tuple[bool, str]:
    try:
        response = requests.get(service.health_url, timeout=2)
        if response.ok:
            return True, response.text
        return False, f"HTTP {response.status_code}"
    except requests.RequestException as exc:
        return False, str(exc)


def service_endpoint(port: str) -> str:
    server_url = os.getenv("SERVER_URL", "127.0.0.1")
    return f"http://{server_url}:{port}/message"


def send_prompt(prompt: str, endpoint: str) -> str:
    response = requests.post(
        endpoint,
        json={"message": prompt},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    payload = response.json()
    if payload.get("error"):
        raise RuntimeError(payload["error"])

    return payload.get("response") or "No response from agent."


def extract_score(text: str) -> float | None:
    match = re.search(r"score\s*:\s*(\d+(?:\.\d+)?)\s*/\s*10", text, re.IGNORECASE)
    return float(match.group(1)) if match else None


def extract_weak_topics(text: str) -> list[str]:
    match = re.search(
        r"weak topics\s*:\s*(.+?)(?:\n[A-Z][A-Za-z ]+\s*:|$)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return []
    raw_topics = re.split(r",|\n|-", match.group(1))
    return [topic.strip(" .") for topic in raw_topics if topic.strip(" .")]


def initialize_state() -> None:
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = [
            {
                "role": "assistant",
                "content": (
                    "Hi, I am your AI Personal University Assistant. Write naturally: "
                    "I can create study plans, simulate exams, tutor you, search the web "
                    "with sources, and give career advice."
                ),
            }
        ]

    if "exam_state" not in st.session_state:
        st.session_state.exam_state = {
            "topic": "",
            "difficulty": "Intermediate",
            "total": 5,
            "number": 0,
            "current_question": "",
            "questions": [],
            "evaluations": [],
            "scores": [],
            "awaiting_answer": False,
        }


def handle_user_message(message: str, endpoint: str) -> tuple[str, list[RouteDecision]]:
    exam_state = st.session_state.exam_state
    decisions = route_user_inputs(
        message,
        awaiting_exam_answer=bool(exam_state.get("awaiting_answer")),
    )

    return _run_decisions_as_structured_response(decisions, message, endpoint), decisions


def _run_decisions_as_structured_response(
    decisions: list[RouteDecision],
    message: str,
    endpoint: str,
) -> str:
    explanation_parts: list[str] = []
    exam_part = ""
    study_part = ""

    for decision in _ordered_decisions(decisions):
        result = _run_decision(decision, message, endpoint)
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


def _ordered_decisions(decisions: list[RouteDecision]) -> list[RouteDecision]:
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


def _run_decision(decision: RouteDecision, message: str, endpoint: str) -> str:
    if decision.mode == "web_search":
        return search_web_with_foundry(message, max_results=decision.source_count)

    if decision.mode == "study_planner":
        prompt = (
            build_study_plan_prompt(
                decision.topic,
                decision.difficulty,
                decision.duration_weeks,
                include_checks=True,
            )
            + f"\n\nOriginal user request:\n{message}"
        )
        response = send_prompt(prompt, endpoint)
        remember_study_plan(decision.topic, decision.difficulty, decision.duration_weeks)
        return response

    if decision.mode == "career_advisor":
        prompt = build_career_prompt(
            target_role=decision.topic,
            current_skills=message,
            interests="Infer interests from the user request when possible.",
            weak_topics=load_memory().get("weak_topics", []),
        )
        response = send_prompt(prompt, endpoint)
        return response

    if decision.mode == "exam_start":
        return _start_exam(decision, endpoint)

    if decision.mode == "exam_answer":
        return _evaluate_exam_answer(message, endpoint)

    if decision.mode == "exam_next":
        return _next_exam_question(endpoint)

    prompt = build_tutor_prompt(message, load_memory().get("weak_topics", []))
    return send_prompt(prompt, endpoint)


def _start_exam(decision: RouteDecision, endpoint: str) -> str:
    st.session_state.exam_state = {
        "topic": decision.topic,
        "difficulty": decision.difficulty,
        "total": 5,
        "number": 1,
        "current_question": "",
        "questions": [],
        "evaluations": [],
        "scores": [],
        "awaiting_answer": True,
    }
    prompt = build_exam_question_prompt(
        decision.topic,
        decision.difficulty,
        1,
        5,
        [],
    )
    question = send_prompt(prompt, endpoint)
    st.session_state.exam_state["current_question"] = question
    st.session_state.exam_state["questions"].append(question)
    return (
        f"I started an exam simulation on **{decision.topic}** "
        f"({decision.difficulty.lower()}, 5 questions).\n\n"
        f"**Question 1/5**\n\n{question}\n\n"
        "Reply directly in the chat and I will evaluate your answer."
    )


def _evaluate_exam_answer(answer: str, endpoint: str) -> str:
    state = st.session_state.exam_state
    if not state.get("current_question"):
        fallback_decision = RouteDecision(
            mode="exam_start",
            topic="the requested topic",
            reason="No active exam question was found.",
        )
        return _start_exam(fallback_decision, endpoint)

    prompt = build_exam_evaluation_prompt(
        state["topic"],
        state["current_question"],
        answer,
    )
    evaluation = send_prompt(prompt, endpoint)
    score = extract_score(evaluation)
    weak_topics = extract_weak_topics(evaluation)
    remember_exam_result(state["topic"], score, evaluation, weak_topics)

    state["evaluations"].append(evaluation)
    if score is not None:
        state["scores"].append(score)
    state["awaiting_answer"] = False

    progress = f"{len(state['scores'])}/{state['total']}"
    average = ""
    if state["scores"]:
        average = f"\n\n**Current average:** {sum(state['scores']) / len(state['scores']):.1f}/10"

    return (
        f"{evaluation}\n\n"
        f"**Exam progress:** {progress}{average}\n\n"
        "Write `next question` to continue."
    )


def _next_exam_question(endpoint: str) -> str:
    state = st.session_state.exam_state
    if not state.get("topic"):
        return (
            "There is no active exam yet. Try: "
            "`Simulate an exam on Azure AI agents`."
        )

    if state["number"] >= state["total"]:
        final_score = sum(state["scores"]) / len(state["scores"]) if state["scores"] else 0
        state["awaiting_answer"] = False
        return f"Esame completato. **Final score: {final_score:.1f}/10**"

    next_number = state["number"] + 1
    prompt = build_exam_question_prompt(
        state["topic"],
        state["difficulty"],
        next_number,
        state["total"],
        state["questions"],
    )
    question = send_prompt(prompt, endpoint)
    state["number"] = next_number
    state["current_question"] = question
    state["questions"].append(question)
    state["awaiting_answer"] = True

    return f"**Question {next_number}/{state['total']}**\n\n{question}\n\nReply directly in the chat."


def render_error(exc: Exception) -> str:
    if isinstance(exc, requests.HTTPError):
        return f"Backend returned an HTTP error: {exc}"
    if isinstance(exc, requests.RequestException):
        return f"Could not reach the selected agent endpoint: {exc}"
    return f"Assistant error: {exc}"


st.set_page_config(
    page_title="AI Personal University Assistant",
    page_icon=":mortar_board:",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .stApp {
        background: #111827;
        color: #eef2f7;
    }
    .hero {
        padding: 1.35rem 1.6rem 1.15rem 1.6rem;
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 8px;
        background: #172033;
        margin-bottom: 1rem;
    }
    .hero h1 {
        color: #f8fbff;
        font-size: 2rem;
        line-height: 1.1;
        margin: 0 0 0.35rem 0;
        letter-spacing: 0;
    }
    .hero p {
        color: rgba(238, 242, 247, 0.84);
        font-size: 1rem;
        max-width: 72rem;
        margin-bottom: 0;
    }
    .status-ok {
        color: #6ee7b7;
        font-weight: 600;
    }
    .status-bad {
        color: #fca5a5;
        font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

initialize_state()
services = get_services()
memory = load_memory()

with st.sidebar:
    st.markdown("## AI Personal University Assistant")
    assistant_port = os.getenv("TITLE_AGENT_PORT", "10007")
    routing_port = os.getenv("ROUTING_AGENT_PORT", "10009")
    backend_mode = st.radio(
        "Backend",
        ["University assistant direct", "Routing agent"],
        horizontal=False,
    )
    active_endpoint = service_endpoint(
        assistant_port if backend_mode == "University assistant direct" else routing_port
    )
    st.caption(f"Active endpoint: `{active_endpoint}`")

    st.markdown("### Services")
    statuses = []
    for service in services:
        is_ok, detail = check_service(service)
        statuses.append(is_ok)
        label = "online" if is_ok else "offline"
        css_class = "status-ok" if is_ok else "status-bad"
        st.markdown(
            f"<span class='{css_class}'>{service.name}: {label}</span>",
            unsafe_allow_html=True,
        )
        with st.expander(f"{service.name} details"):
            st.code(service.health_url)
            st.caption(detail[:300])

    st.markdown("---")
    st.markdown("### Routing Map")
    st.caption("Free text is classified automatically.")
    st.markdown(
        """
        - Multiple tasks are executed in sequence
        - Results are merged into one response
        - Output sections: Explanation, Exam Question, Study Plan
        - `explain`, `spiegami` -> Explanation
        - `quiz`, `exam`, `interrogami` -> Exam Question
        - `study plan`, `prepare`, `roadmap` -> Study Plan
        """
    )

    st.markdown("### Memory")
    weak_topics = memory.get("weak_topics", [])
    if weak_topics:
        st.caption("Weak topics")
        st.write(", ".join(weak_topics))
    else:
        st.caption("No weak topics recorded yet.")

    exam_results = memory.get("exam_results", [])
    scored_results = [item["score"] for item in exam_results if item.get("score") is not None]
    if scored_results:
        st.metric("Average exam score", f"{sum(scored_results) / len(scored_results):.1f}/10")

    st.markdown("---")
    if st.button("Reset chat", use_container_width=True):
        st.session_state.chat_messages = []
        st.session_state.exam_state = {
            "topic": "",
            "difficulty": "Intermediate",
            "total": 5,
            "number": 0,
            "current_question": "",
            "questions": [],
            "evaluations": [],
            "scores": [],
            "awaiting_answer": False,
        }
        st.rerun()

st.markdown(
    """
    <div class="hero">
        <h1>AI Personal University Assistant</h1>
        <p>
            One chat for study planning, exam simulation, tutoring, web search with sources,
            and career advice. Write naturally; the assistant routes the request automatically.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

if not any(statuses):
    st.warning(
        "Backend services are offline. Start them with `python run_all.py`, then refresh this page."
    )

for message in st.session_state.chat_messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

user_message = st.chat_input("Ask anything: study plan, exam, tutoring, web search, or career advice")
if user_message:
    st.session_state.chat_messages.append({"role": "user", "content": user_message})
    with st.chat_message("user"):
        st.markdown(user_message)

    with st.chat_message("assistant"):
        with st.spinner("Routing and thinking..."):
            try:
                assistant_response, _decision = handle_user_message(user_message, active_endpoint)
            except Exception as exc:
                assistant_response = render_error(exc)
            st.markdown(assistant_response)

    st.session_state.chat_messages.append(
        {"role": "assistant", "content": assistant_response}
    )
