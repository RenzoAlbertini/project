"""Streamlit web UI for the Azure AI Study Planner demo."""

from __future__ import annotations

import os
from dataclasses import dataclass

import requests
import streamlit as st
from dotenv import load_dotenv

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
        Service("Study planner", os.getenv("TITLE_AGENT_PORT", "10007")),
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


def build_prompt(topic: str, difficulty: str, duration: int, include_checks: bool) -> str:
    prompt = (
        f"Create a {difficulty.lower()} study plan for {topic}. "
        f"Duration: {duration} weeks. "
        "Include weekly milestones, practical exercises, and a final mini project."
    )
    if include_checks:
        prompt += " Include checkpoints and short self-assessment questions."
    return prompt


st.set_page_config(
    page_title="AI Study Path Planner",
    page_icon=":mortar_board:",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .stApp {
        background: linear-gradient(180deg, #07111f 0%, #0c1828 48%, #102235 100%);
        color: #e8eef9;
    }
    .hero {
        padding: 2rem 2rem 1.5rem 2rem;
        border: 1px solid rgba(255,255,255,0.10);
        border-radius: 12px;
        background: rgba(8, 16, 30, 0.72);
        box-shadow: 0 18px 48px rgba(0, 0, 0, 0.22);
    }
    .hero h1 {
        color: #f8fbff;
        font-size: 2.6rem;
        line-height: 1.08;
        margin: 0 0 0.4rem 0;
        letter-spacing: 0;
    }
    .hero p {
        color: rgba(232, 238, 249, 0.84);
        font-size: 1rem;
        max-width: 64rem;
        margin-bottom: 0;
    }
    .status-ok {
        color: #7dd3a8;
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

services = get_services()

with st.sidebar:
    st.markdown("## AI Study Path Planner")
    title_port = os.getenv("TITLE_AGENT_PORT", "10007")
    routing_port = os.getenv("ROUTING_AGENT_PORT", "10009")
    backend_mode = st.radio(
        "Backend",
        ["Study planner direct", "Routing agent"],
        horizontal=False,
    )
    active_endpoint = service_endpoint(
        title_port if backend_mode == "Study planner direct" else routing_port
    )
    st.caption(f"Active endpoint: `{active_endpoint}`")

    st.markdown("### Backend")
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
    topic = st.text_input("Topic", value="Azure AI agents")
    difficulty = st.selectbox(
        "Difficulty",
        ["Beginner", "Intermediate", "Advanced"],
        index=1,
    )
    duration = st.slider("Duration in weeks", 2, 16, 4)
    include_checks = st.toggle("Include checkpoints", value=True)

st.markdown(
    """
    <div class="hero">
        <h1>AI Study Path Planner</h1>
        <p>
            An Azure Foundry + A2A workspace that turns a learning goal into a clear, practical study path.
            Tune the goal, check the agents, and generate a plan ready to follow.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

prompt_template = build_prompt(topic, difficulty, duration, include_checks)

left, right = st.columns([1, 1.35], gap="large")

with left:
    st.subheader("Request")
    with st.form("study_plan_form"):
        prompt = st.text_area(
            "Prompt",
            value=prompt_template,
            height=210,
        )
        submit = st.form_submit_button(
            "Generate study plan",
            use_container_width=True,
            type="primary",
        )

    if not all(statuses):
        st.warning(
            "Some backend services are offline. Start them with `python run_all.py`, "
            "then refresh this page."
        )

with right:
    st.subheader("Output")
    if submit:
        if not prompt.strip():
            st.error("Write a prompt before generating a study plan.")
        else:
            with st.spinner("Generating the study plan..."):
                try:
                    result = send_prompt(prompt.strip(), active_endpoint)
                    st.success("Study plan generated")
                    st.markdown(result)
                except requests.HTTPError as exc:
                    st.error(f"Backend returned an HTTP error: {exc}")
                except requests.RequestException as exc:
                    st.error(f"Could not reach the routing agent: {exc}")
                except RuntimeError as exc:
                    st.error(f"Routing agent error: {exc}")
    else:
        st.info("Adjust the request and generate a plan when the backend is online.")
        st.markdown(
            """
            The expected local services are:

            - Study planner agent on port `10007`
            - Outline agent on port `10008`
            - Routing agent on port `10009`
            - Streamlit UI on port `8501`
            """
        )
