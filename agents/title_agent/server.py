import os
import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route

from agents.title_agent.agent_executor import STUDY_PLAN_INSTRUCTIONS, create_foundry_agent_executor
from agents.title_agent.foundry_client import FoundryClient

load_dotenv()

host = os.environ["SERVER_URL"]
port = os.environ["TITLE_AGENT_PORT"]



# Define available agent skills
skills = [
    AgentSkill(
        id='generate_study_plan',
        name='Generate Study Plan',
        description='Creates a structured study plan for a given topic.',
        tags=['study', 'planning'],
        examples=[
            'Can you create a study plan for machine learning?',
            'I want to learn React step by step',
        ],
    ),
    AgentSkill(
        id='simulate_exam',
        name='Simulate Exam',
        description='Asks exam questions one by one and evaluates student answers.',
        tags=['exam', 'assessment', 'feedback'],
        examples=[
            'Ask me an intermediate exam question about neural networks.',
            'Evaluate my answer and tell me what to review.',
        ],
    ),
    AgentSkill(
        id='career_advice',
        name='Career Advice',
        description='Suggests skills, project ideas, and learning actions for a target role.',
        tags=['career', 'skills', 'projects'],
        examples=[
            'How should I prepare for an AI engineer role?',
        ],
    ),
]

# Configure agent card for A2A service discovery
agent_card = AgentCard(
    name='Microsoft Foundry University Assistant Agent',
    description=(
        'An intelligent university assistant powered by Foundry. '
        'It supports study planning, exam practice, tutoring, and career guidance.'
    ),
    url=f'http://{host}:{port}/',
    version='1.0.0',
    default_input_modes=['text'],
    default_output_modes=['text'],
    capabilities=AgentCapabilities(),
    skills=skills,
)



# Initialize executor for A2A protocol
agent_executor = create_foundry_agent_executor(agent_card)

# Configure request handler with in-memory task storage
request_handler = DefaultRequestHandler(
    agent_executor=agent_executor,
    task_store=InMemoryTaskStore()
)

# Create A2A-compliant application

a2a_app = A2AStarletteApplication(
    agent_card=agent_card,
    http_handler=request_handler
)

routes = a2a_app.routes()
direct_foundry_client: FoundryClient | None = None

# Health check endpoint
async def health_check(request: Request) -> PlainTextResponse:
    """Health check endpoint for service monitoring."""
    return PlainTextResponse('University Assistant Agent is running!')


async def handle_message(request: Request) -> JSONResponse:
    """Simple JSON endpoint used by the local Streamlit demo UI."""
    global direct_foundry_client

    data = await request.json()
    user_message = (data.get("message") or "").strip()
    if not user_message:
        return JSONResponse({"error": "No message provided."}, status_code=400)

    try:
        if direct_foundry_client is None:
            direct_foundry_client = FoundryClient()

        response = direct_foundry_client.run(
            user_message,
            instructions=STUDY_PLAN_INSTRUCTIONS,
        )
        return JSONResponse({"response": response or "No response from agent."})
    except Exception as exc:
        return JSONResponse(
            {"error": f"University Assistant failed to process the request: {exc}"},
            status_code=500,
        )

routes.append(
    Route(path='/health', methods=['GET'], endpoint=health_check)
)
routes.append(
    Route(path='/message', methods=['POST'], endpoint=handle_message)
)

# Initialize Starlette application

app = Starlette(routes=routes)


def main():
    uvicorn.run(app, host=host, port=int(port))


if __name__ == '__main__':
    main()
