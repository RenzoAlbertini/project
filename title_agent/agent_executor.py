"""Azure AI Foundry agent executor with local tool handling."""

from __future__ import annotations

from a2a.server.events.event_queue import EventQueue
from a2a.server.agent_execution import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.tasks import TaskUpdater
from a2a.utils import new_agent_text_message
from a2a.types import AgentCard, Part, TaskState
from title_agent.foundry_client import FoundryClient

STUDY_PLAN_INSTRUCTIONS = (
    'You are a study plan assistant with an encouraging, clear, and professional tone, like a university tutor or senior developer. '
    'At the beginning of each plan, write a brief introduction explaining why that topic matters in the real world. '
    'Generate only the requested study plan. Do not save files. '
    'Conclude the plan completely and ready to copy to a text file, but do not ask for saving.'
)


class FoundryAgentExecutor(AgentExecutor):

    def __init__(self, card: AgentCard):
        self._card = card
        self._foundry_client = FoundryClient()

    def _extract_user_message(self, message_parts: list[Part]) -> str:
        for part in message_parts:
            text = getattr(getattr(part, 'root', None), 'text', None)
            if text:
                return text
        raise ValueError('No text message found in A2A message parts.')

    def _generate_study_plan(self, user_message: str) -> str:
        final_text = self._foundry_client.run(
            user_message,
            instructions=STUDY_PLAN_INSTRUCTIONS,
        ).strip()
        if final_text:
            return final_text

        return 'Failed to generate study plan.'

    async def _process_request(
        self,
        message_parts: list[Part],
        context_id: str,
        task_updater: TaskUpdater
    ) -> None:

        # Process a user request through the Foundry agent
        try:

            user_message = self._extract_user_message(message_parts)

            # Update task status to working
            await task_updater.update_status(
                TaskState.working,
                message=new_agent_text_message(
                    'Study Planner is processing your request...',
                    context_id=context_id
                ),
            )

            study_plan = self._generate_study_plan(user_message)
            responses = [study_plan]

            # Update task with generated study plan
            for response in responses:
                await task_updater.update_status(
                    TaskState.working,
                    message=new_agent_text_message(
                        response,
                        context_id=context_id
                    ),
                )

            # Mark the task as complete
            final_message = responses[-1] if responses else 'Task completed.'
            await task_updater.complete(
                message=new_agent_text_message(
                    final_message,
                    context_id=context_id
                )
            )

        except Exception as e:
            print(f'Study Planner: Error processing request - {e}')
            await task_updater.failed(
                message=new_agent_text_message(
                    f'Study Planner failed to process the request: {e}',
                    context_id=context_id
                )
            )

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ):
        """Execute study plan generation request."""
        updater = TaskUpdater(
            event_queue,
            context.task_id,
            context.context_id
        )

        await updater.submit()
        await updater.start_work()
        await self._process_request(
            context.message.parts,
            context.context_id,
            updater
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue):
        """Cancel study plan generation request."""
        print(f'Study Planner: Cancelling execution for context {context.context_id}')

        updater = TaskUpdater(
            event_queue,
            context.task_id,
            context.context_id
        )

        await updater.failed(
            message=new_agent_text_message(
                'Task cancelled by user.',
                context_id=context.context_id
            )
        )


def create_foundry_agent_executor(card: AgentCard) -> FoundryAgentExecutor:
    return FoundryAgentExecutor(card)
