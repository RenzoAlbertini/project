import os

import requests
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()


class FoundryClient:
    """Azure Foundry OpenAI client wrapper for study plan generation."""

    def __init__(self):
        """Initialize Foundry client with Azure identity credentials."""
        self.credential = DefaultAzureCredential()
        self.endpoint = os.environ["FOUNDRY_AGENT_ENDPOINT"]
        self.api_version = os.getenv("FOUNDRY_API_VERSION", "v1")
        self.model = os.getenv("FOUNDRY_AGENT_MODEL", os.environ["MODEL_DEPLOYMENT_NAME"])

    def run(self, message: str, instructions: str | None = None) -> str:
        """Send message to Foundry agent and return text response."""
        return self._run_with_endpoint(self.endpoint, message, instructions)

    def _run_with_endpoint(self, endpoint: str, message: str, instructions: str | None = None) -> str:
        input_text = message
        normalized_endpoint = endpoint.replace("\\", "/")
        use_agent_endpoint = "/agents/" in normalized_endpoint
        if instructions and use_agent_endpoint:
            input_text = f"{instructions}\n\nUser request:\n{message}"

        request_body = {
            "model": self.model,
            "input": input_text,
        }
        if instructions and not use_agent_endpoint:
            request_body["instructions"] = instructions

        token = self.credential.get_token("https://ai.azure.com/.default").token
        response = requests.post(
            endpoint,
            params=self._request_params(endpoint),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=request_body,
            timeout=120,
        )
        if not response.ok:
            fallback_endpoint = self._fallback_responses_endpoint(endpoint, response)
            if fallback_endpoint:
                return self._run_with_endpoint(fallback_endpoint, message, instructions)

            raise RuntimeError(
                f"Foundry request failed with HTTP {response.status_code}: {response.text}"
            )

        payload = response.json()
        output_text = (payload.get("output_text") or "").strip()
        if output_text:
            return output_text

        texts = []
        for item in payload.get("output", []):
            for content in item.get("content", []):
                text = content.get("text")
                if text:
                    texts.append(text)

        return "\n".join(texts).strip()

    def _request_params(self, endpoint: str) -> dict[str, str]:
        if "/openai/v1/" in endpoint.replace("\\", "/"):
            return {}
        return {"api-version": self.api_version}

    def _fallback_responses_endpoint(self, endpoint: str, response: requests.Response) -> str | None:
        """Fallback from a stale agent endpoint to the project-level Responses API."""
        if response.status_code != 404 or "/agents/" not in endpoint.replace("\\", "/"):
            return None

        project_endpoint = os.getenv("PROJECT_ENDPOINT")
        if not project_endpoint:
            return None

        return f"{project_endpoint.rstrip('/')}/openai/v1/responses"
