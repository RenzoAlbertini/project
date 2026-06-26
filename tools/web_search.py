"""Optional web search helpers with source formatting."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests
from azure.identity import DefaultAzureCredential


SEARCH_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str


def search_web(query: str, max_results: int = 5) -> list[SearchResult]:
    """Search the web using Bing when configured, otherwise DuckDuckGo."""
    cleaned_query = query.strip()
    if not cleaned_query:
        return []

    bing_key = os.getenv("BING_SEARCH_KEY")
    if bing_key:
        return _search_bing(cleaned_query, max_results, bing_key)

    return _search_duckduckgo(cleaned_query, max_results)


def format_search_results(results: list[SearchResult]) -> str:
    if not results:
        return "No web results were returned."

    lines = []
    for index, result in enumerate(results, start=1):
        lines.append(
            f"**{index}. [{result.title}]({result.url})**\n\n"
            f"{result.snippet}\n\n"
            f"Source: `{result.source}`"
        )
    return "\n\n".join(lines)


def search_web_with_foundry(query: str, max_results: int = 5) -> str:
    """Search with Azure Foundry Responses web search and return markdown with citations."""
    cleaned_query = query.strip()
    if not cleaned_query:
        return "Write a search query first."

    project_endpoint = os.getenv("PROJECT_ENDPOINT")
    model = os.getenv("MODEL_DEPLOYMENT_NAME") or os.getenv("FOUNDRY_AGENT_MODEL")
    if not project_endpoint or not model:
        raise RuntimeError("PROJECT_ENDPOINT and MODEL_DEPLOYMENT_NAME must be set for Foundry web search.")

    prompt = (
        f"Search the web for: {cleaned_query}\n\n"
        f"Return up to {max_results} useful results. For each result include a short summary and the source URL. "
        "Prefer authoritative and current sources."
    )

    payload = _post_foundry_web_search(project_endpoint, model, prompt, "web_search")
    if payload.get("error"):
        payload = _post_foundry_web_search(project_endpoint, model, prompt, "web_search_preview")

    text, citations = _extract_foundry_text_and_citations(payload)
    if not text and not citations:
        return "Azure Foundry web search completed, but no text or citations were returned."

    if citations:
        text = f"{text.strip()}\n\n### Sources\n{_format_citations(citations[:max_results])}"

    return text.strip()


def _search_bing(query: str, max_results: int, key: str) -> list[SearchResult]:
    endpoint = os.getenv("BING_SEARCH_ENDPOINT", "https://api.bing.microsoft.com/v7.0/search")
    response = requests.get(
        endpoint,
        params={"q": query, "count": max_results, "responseFilter": "Webpages"},
        headers={"Ocp-Apim-Subscription-Key": key},
        timeout=SEARCH_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    payload = response.json()
    pages = payload.get("webPages", {}).get("value", [])
    return [
        SearchResult(
            title=item.get("name", "Untitled result"),
            url=item.get("url", ""),
            snippet=item.get("snippet", ""),
            source="Bing Web Search",
        )
        for item in pages
        if item.get("url")
    ]


def _post_foundry_web_search(
    project_endpoint: str,
    model: str,
    prompt: str,
    tool_type: str,
) -> dict[str, Any]:
    endpoint = f"{project_endpoint.rstrip('/')}/openai/v1/responses"
    token = DefaultAzureCredential().get_token("https://ai.azure.com/.default").token
    response = requests.post(
        endpoint,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "input": prompt,
            "tools": [{"type": tool_type}],
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.json()


def _extract_foundry_text_and_citations(payload: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    text_parts: list[str] = []
    citations_by_url: dict[str, dict[str, str]] = {}

    output_text = (payload.get("output_text") or "").strip()
    if output_text:
        text_parts.append(output_text)

    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue

        for content in item.get("content", []):
            text = content.get("text")
            if text:
                text_parts.append(text)

            for annotation in content.get("annotations", []):
                if annotation.get("type") != "url_citation" or not annotation.get("url"):
                    continue
                citations_by_url.setdefault(
                    annotation["url"],
                    {
                        "title": annotation.get("title") or annotation["url"],
                        "url": annotation["url"],
                    },
                )

    return "\n\n".join(text_parts).strip(), list(citations_by_url.values())


def _format_citations(citations: list[dict[str, str]]) -> str:
    lines = []
    for index, citation in enumerate(citations, start=1):
        lines.append(f"{index}. [{citation['title']}]({citation['url']})")
    return "\n".join(lines)


def _search_duckduckgo(query: str, max_results: int) -> list[SearchResult]:
    response = requests.get(
        "https://api.duckduckgo.com/",
        params={
            "q": query,
            "format": "json",
            "no_redirect": "1",
            "no_html": "1",
        },
        timeout=SEARCH_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    payload = response.json()
    results: list[SearchResult] = []

    if payload.get("AbstractURL"):
        results.append(
            SearchResult(
                title=payload.get("Heading") or query,
                url=payload["AbstractURL"],
                snippet=payload.get("AbstractText", ""),
                source="DuckDuckGo Instant Answer",
            )
        )

    for topic in payload.get("RelatedTopics", []):
        _collect_duckduckgo_topic(topic, results)
        if len(results) >= max_results:
            break

    return results[:max_results]


def _collect_duckduckgo_topic(topic: dict[str, Any], results: list[SearchResult]) -> None:
    if "Topics" in topic:
        for nested in topic["Topics"]:
            _collect_duckduckgo_topic(nested, results)
        return

    url = topic.get("FirstURL")
    text = topic.get("Text")
    if not url or not text:
        return

    title = text.split(" - ", 1)[0][:90]
    results.append(
        SearchResult(
            title=title,
            url=url,
            snippet=text,
            source="DuckDuckGo Instant Answer",
        )
    )
