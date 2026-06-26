import asyncio
import json
import logging
import os
import uuid
import httpx

from typing import Any, Callable
from azure.ai.agents import AgentsClient
from azure.identity import DefaultAzureCredential
from azure.ai.agents.models import ListSortOrder, FunctionTool, MessageRole
from collections.abc import Callable
from dotenv import load_dotenv

from a2a.client import A2ACardResolver, A2AClient
from a2a.types import (
    AgentCard,
    MessageSendParams,
    SendMessageRequest,
    SendMessageResponse,
    SendMessageSuccessResponse,
    Task,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
)

load_dotenv()
logger = logging.getLogger(__name__)

TaskCallbackArg = Task | TaskStatusUpdateEvent | TaskArtifactUpdateEvent
TaskUpdateCallback = Callable[[TaskCallbackArg, AgentCard], Task]


class RemoteAgentConnections:
    """Holds connection to a remote A2A agent."""

    def __init__(self, agent_card: AgentCard, agent_url: str):
        self._httpx_client = httpx.AsyncClient(timeout=30)
        self.agent_client = A2AClient(self._httpx_client, agent_card, url=agent_url)
        self.card = agent_card

    def get_agent(self) -> AgentCard:
        return self.card

    async def send_message(self, message_request: SendMessageRequest) -> SendMessageResponse:
        return await self.agent_client.send_message(message_request)


class RoutingAgent:

    def __init__(self, task_callback: TaskUpdateCallback | None = None):

        self.task_callback = task_callback
        self.remote_agent_connections: dict[str, RemoteAgentConnections] = {}
        self.cards: dict[str, AgentCard] = {}

        self.agents_client = AgentsClient(
            endpoint=os.environ["PROJECT_ENDPOINT"],
            credential=DefaultAzureCredential(
                exclude_environment_credential=True,
                exclude_managed_identity_credential=True
            )
        )

        self.azure_agent = None
        self.current_thread = None

    @classmethod
    async def create(cls, remote_agent_addresses: list[str], task_callback: TaskUpdateCallback | None = None) -> "RoutingAgent":
        instance = cls(task_callback)
        await instance._async_init_components(remote_agent_addresses)
        return instance

    def list_remote_agents(self) -> str:
        if not self.remote_agent_connections:
            return "[]"

        lines = []
        for card in self.cards.values():
            lines.append(f"{card.name}: {card.description}")

        return "[\n  " + ",\n  ".join(lines) + "\n]"

    async def _async_init_components(self, remote_agent_addresses: list[str]) -> None:

        async with httpx.AsyncClient(timeout=30) as client:
            for address in remote_agent_addresses:
                card_resolver = A2ACardResolver(client, address)
                try:
                    card = await card_resolver.get_agent_card()

                    remote_connection = RemoteAgentConnections(
                        agent_card=card,
                        agent_url=address
                    )

                    self.remote_agent_connections[card.name] = remote_connection
                    self.cards[card.name] = card

                except Exception as exc:
                    logger.warning("Failed to initialize remote agent at %s: %s", address, exc)

        logger.info("Found remote agents: %s", self.list_remote_agents())

    async def send_message(self, agent_name: str, task: str):

        if agent_name not in self.remote_agent_connections:
            raise ValueError(f"Agent {agent_name} not found")

        # Retrieve client
        client = self.remote_agent_connections[agent_name]

        message_id = str(uuid.uuid4())

        # Payload
        payload: dict[str, Any] = {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": task}],
                "messageId": message_id,
            },
        }

        message_request = SendMessageRequest(
            id=message_id,
            params=MessageSendParams.model_validate(payload)
        )

        # SEND (FIXED ERROR HERE)
        send_response: SendMessageResponse = await client.send_message(
            message_request=message_request
        )

        if not isinstance(send_response.root, SendMessageSuccessResponse):
            logger.warning("Remote A2A agent returned a non-success response")
            return

        if not isinstance(send_response.root.result, Task):
            logger.warning("Remote A2A agent returned a non-task response")
            return

        return send_response.root.result

    def create_agent(self):

        functions = FunctionTool({self.send_message})

        self.azure_agent = self.agents_client.create_agent(
            model=os.environ["MODEL_DEPLOYMENT_NAME"],
            name="routing-agent",
            instructions=f"""
            You are a Routing Agent.

            Your job:
            - route user requests to correct remote agent
            - manage delegation

            Available agents:
            {self.list_remote_agents()}
            """,
            tools=functions.definitions
        )

        self.current_thread = self.agents_client.threads.create()

        return self.azure_agent

    async def process_user_message(self, user_message: str) -> str:

        self.agents_client.messages.create(
            thread_id=self.current_thread.id,
            role=MessageRole.USER,
            content=user_message
        )

        run = self.agents_client.runs.create(
            thread_id=self.current_thread.id,
            agent_id=self.azure_agent.id
        )

        while run.status in ["queued", "in_progress", "requires_action"]:
            await asyncio.sleep(1)
            run = self.agents_client.runs.get(
                thread_id=self.current_thread.id,
                run_id=run.id
            )

            if run.status == "requires_action":

                tool_calls = run.required_action.submit_tool_outputs.tool_calls
                tool_outputs = []

                for tool_call in tool_calls:

                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)

                    if function_name == "send_message":

                        result = await self.send_message(
                            agent_name=function_args["agent_name"],
                            task=function_args["task"]
                        )

                        output = json.dumps(str(result))

                    else:
                        output = json.dumps({"error": "unknown function"})

                    tool_outputs.append({
                        "tool_call_id": tool_call.id,
                        "output": output
                    })

                self.agents_client.runs.submit_tool_outputs(
                    thread_id=self.current_thread.id,
                    run_id=run.id,
                    tool_outputs=tool_outputs
                )

        if run.status == "failed":
            return f"Error: {run.last_error}"

        messages = self.agents_client.messages.list(
            thread_id=self.current_thread.id,
            order=ListSortOrder.DESCENDING
        )

        for msg in messages:
            if msg.role == MessageRole.AGENT and msg.text_messages:
                return msg.text_messages[-1].text.value

        return "No response"

