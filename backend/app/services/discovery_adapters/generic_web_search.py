from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib import parse

from pydantic import ValidationError

from app.schemas.discovery import DiscoveredSource
from app.services.public_fetch import PublicFetchClient
from app.services.discovery_adapters.virginia_scc import DiscoveryAdapterResult
from app.services.source_registry import SourceRegistryEntry


GENERIC_WEB_SEARCH_ADAPTER_ID = "generic_web_search"
GENERIC_WEB_SEARCH_METHOD = "web_search_pattern"
DEFAULT_RESULT_LIMIT = 10
DEFAULT_MOCK_RESULTS_PATH = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "generic_web_search_results.json"
BRAVE_SEARCH_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
REQUIRES_PROVIDER_WARNING = "generic_web_search_requires_search_api"
MISSING_API_KEY_WARNING = "web_search_api_key_missing"
UNSUPPORTED_PROVIDER_WARNING = "web_search_provider_unsupported"
PROVIDER_ERROR_WARNING = "generic_web_search_provider_error"
POSITIVE_RELEVANCE_TERMS = {
    "data center",
    "datacenter",
    "large load",
    "electric service agreement",
    "transmission interconnection",
    "interconnection",
    "planning commission",
    "rezoning",
    "special use permit",
    "conditional use permit",
    "planning agenda",
    "city council",
    "economic development",
    "industrial development authority",
    "press release",
    "hyperscale",
    "campus",
    "utility filing",
    "special contract",
    "load interconnection",
}
IRRELEVANT_TERMS = {
    "server rack for sale",
    "jobs at data center",
    "data center training",
    "crypto mining",
    "definition of data center",
    "what is a data center",
}


@dataclass
class WebSearchResult:
    url: str
    title: str | None = None
    snippet: str | None = None
    publisher: str | None = None
    raw_metadata: dict[str, Any] = field(default_factory=dict)


class WebSearchProvider(Protocol):
    provider_id: str

    def search(self, query: str, *, limit: int = DEFAULT_RESULT_LIMIT) -> list[WebSearchResult]:
        ...


class WebSearchProviderRuntimeError(RuntimeError):
    pass


class DisabledWebSearchProvider:
    provider_id = "disabled"
    config_warning = REQUIRES_PROVIDER_WARNING

    def search(self, query: str, *, limit: int = DEFAULT_RESULT_LIMIT) -> list[WebSearchResult]:
        raise RuntimeError(REQUIRES_PROVIDER_WARNING)


class MissingApiKeyWebSearchProvider:
    config_warning = MISSING_API_KEY_WARNING

    def __init__(self, provider_id: str):
        self.provider_id = provider_id

    def search(self, query: str, *, limit: int = DEFAULT_RESULT_LIMIT) -> list[WebSearchResult]:
        raise RuntimeError(MISSING_API_KEY_WARNING)


class UnsupportedWebSearchProvider:
    config_warning = UNSUPPORTED_PROVIDER_WARNING

    def __init__(self, provider_id: str):
        self.provider_id = provider_id

    def search(self, query: str, *, limit: int = DEFAULT_RESULT_LIMIT) -> list[WebSearchResult]:
        raise RuntimeError(UNSUPPORTED_PROVIDER_WARNING)


class MockWebSearchProvider:
    provider_id = "mock"

    def __init__(self, results_by_query: dict[str, list[dict[str, Any]]]):
        self.results_by_query = results_by_query
        self.calls: list[str] = []

    @classmethod
    def from_path(cls, path: Path) -> MockWebSearchProvider:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("queries"), dict):
            return cls(payload["queries"])
        if isinstance(payload, dict):
            return cls(payload)
        raise ValueError("mock web-search fixture must be a JSON object")

    def search(self, query: str, *, limit: int = DEFAULT_RESULT_LIMIT) -> list[WebSearchResult]:
        self.calls.append(query)
        rows = self.results_by_query.get(query, [])
        results: list[WebSearchResult] = []
        for row in rows[:limit]:
            if not isinstance(row, dict):
                continue
            url = clean_text(row.get("url") or row.get("source_url"))
            if not url:
                continue
            results.append(
                WebSearchResult(
                    url=url,
                    title=clean_text(row.get("title") or row.get("source_title")),
                    snippet=clean_text(row.get("snippet")),
                    publisher=clean_text(row.get("publisher")),
                    raw_metadata={
                        key: value
                        for key, value in row.items()
                        if key not in {"url", "source_url", "title", "source_title", "snippet", "publisher"}
                    },
                )
            )
        return results


class BraveWebSearchProvider:
    provider_id = "brave"

    def __init__(
        self,
        *,
        api_key: str,
        fetch_client: PublicFetchClient | None = None,
        endpoint: str = BRAVE_SEARCH_ENDPOINT,
    ):
        self.api_key = api_key
        self.fetch_client = fetch_client or PublicFetchClient()
        self.endpoint = endpoint

    def search(self, query: str, *, limit: int = DEFAULT_RESULT_LIMIT) -> list[WebSearchResult]:
        url = f"{self.endpoint}?{parse.urlencode({'q': query, 'count': str(limit)})}"
        fetch_result = self.fetch_client.fetch(
            url,
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": self.api_key,
            },
        )
        if not fetch_result.ok or fetch_result.text is None:
            raise WebSearchProviderRuntimeError(
                f"brave_search_request_failed: {fetch_result.error_type or 'fetch_error'}; "
                f"{fetch_result.error_message or 'no detail'}"
            )
        try:
            payload = json.loads(fetch_result.text)
        except json.JSONDecodeError as exc:
            raise WebSearchProviderRuntimeError(f"brave_search_invalid_json: {exc}") from exc
        return parse_brave_search_response(payload)


class GenericWebSearchDiscoveryAdapter:
    adapter_id = GENERIC_WEB_SEARCH_ADAPTER_ID

    def __init__(
        self,
        source: SourceRegistryEntry,
        *,
        provider: WebSearchProvider | None = None,
        result_limit: int = DEFAULT_RESULT_LIMIT,
    ):
        if source.discovery_method != GENERIC_WEB_SEARCH_METHOD:
            raise ValueError(f"Generic web-search adapter cannot run method {source.discovery_method!r}")
        self.source = source
        self.provider = provider if provider is not None else provider_from_env()
        self.result_limit = result_limit_from_env(default=result_limit) if provider is None else result_limit

    def run(self, *, dry_run: bool, allow_insecure_fetch: bool = False) -> DiscoveryAdapterResult:
        result = DiscoveryAdapterResult(
            adapter_id=self.adapter_id,
            source_id=self.source.id,
            planned_queries=self.planned_queries(),
        )
        if dry_run:
            result.warnings.append("dry_run_only: generic web-search adapter did not call a search provider")
            return result
        config_warning = getattr(self.provider, "config_warning", None)
        if config_warning:
            result.warnings.extend(provider_config_warnings(self.provider.provider_id, config_warning))
            return result

        parsed_results: list[tuple[str, WebSearchResult]] = []
        for query in self.source.search_terms:
            try:
                provider_results = self.provider.search(query, limit=self.result_limit)
            except Exception as exc:  # noqa: BLE001 - providers are optional external integrations.
                result.warnings.append(
                    f"{PROVIDER_ERROR_WARNING} for {self.source.id} via {self.provider.provider_id}: "
                    f"{type(exc).__name__}: {exc}"
                )
                continue
            for provider_result in provider_results:
                if is_relevant_result(provider_result, query=query):
                    parsed_results.append((query, provider_result))

        result.discovered_sources.extend(self._sources_from_results(parsed_results))
        if not result.discovered_sources:
            result.warnings.append(f"no_generic_web_search_results for source {self.source.id}")
        return result

    def planned_queries(self) -> list[dict[str, str]]:
        return [
            {
                "term": term,
                "search_url": build_search_url(str(self.source.base_url), term),
                "action": "query_configured_web_search_provider",
            }
            for term in self.source.search_terms
        ]

    def _sources_from_results(self, results: list[tuple[str, WebSearchResult]]) -> list[DiscoveredSource]:
        discovered: list[DiscoveredSource] = []
        seen_urls: set[str] = set()
        for search_term, search_result in results:
            normalized_url = normalize_url(search_result.url)
            if normalized_url in seen_urls:
                continue
            seen_urls.add(normalized_url)
            try:
                discovered.append(
                    DiscoveredSource(
                        source_url=normalized_url,
                        source_title=search_result.title,
                        source_type=self.source.source_type,
                        publisher=search_result.publisher or infer_publisher(normalized_url),
                        geography=self.source.geography,
                        discovered_at=datetime.now(timezone.utc),
                        discovery_method=self.source.discovery_method,
                        confidence="candidate_discovered",
                        notes=build_notes(self.source, search_term, self.provider.provider_id),
                        search_term=search_term,
                        source_query=search_term,
                        snippet=search_result.snippet,
                        source_registry_id=self.source.id,
                        adapter_id=self.adapter_id,
                        raw_metadata_json={
                            "provider": self.provider.provider_id,
                            "source_registry_id": self.source.id,
                            "adapter_id": self.adapter_id,
                            "search_term": search_term,
                            "provider_metadata": search_result.raw_metadata,
                        },
                    )
                )
            except ValidationError:
                continue
        return discovered


def provider_from_env() -> WebSearchProvider:
    provider = os.getenv("WEB_SEARCH_PROVIDER", "disabled").strip().lower() or "disabled"
    if provider == "disabled":
        return DisabledWebSearchProvider()
    if provider == "mock":
        path_text = os.getenv("WEB_SEARCH_MOCK_RESULTS_PATH") or str(DEFAULT_MOCK_RESULTS_PATH)
        try:
            return MockWebSearchProvider.from_path(Path(path_text))
        except (OSError, ValueError, json.JSONDecodeError):
            return DisabledWebSearchProvider()
    if provider == "brave":
        api_key = clean_text(os.getenv("WEB_SEARCH_API_KEY"))
        if not api_key:
            return MissingApiKeyWebSearchProvider(provider)
        return BraveWebSearchProvider(api_key=api_key)
    if provider in {"serpapi", "tavily"}:
        return UnsupportedWebSearchProvider(provider)
    return DisabledWebSearchProvider()


def configured_provider_name() -> str:
    return os.getenv("WEB_SEARCH_PROVIDER", "disabled").strip().lower() or "disabled"


def result_limit_from_env(*, default: int = DEFAULT_RESULT_LIMIT) -> int:
    raw = os.getenv("WEB_SEARCH_MAX_RESULTS")
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return min(max(value, 1), DEFAULT_RESULT_LIMIT)


def provider_config_warnings(provider_id: str, warning_code: str) -> list[str]:
    if warning_code == REQUIRES_PROVIDER_WARNING:
        return [
            REQUIRES_PROVIDER_WARNING,
            "Set WEB_SEARCH_PROVIDER=mock for fixture-backed runs, or WEB_SEARCH_PROVIDER=brave with "
            "WEB_SEARCH_API_KEY for Brave Search API runs. Direct Google HTML scraping is disabled.",
        ]
    if warning_code == MISSING_API_KEY_WARNING:
        return [f"{MISSING_API_KEY_WARNING}: WEB_SEARCH_API_KEY is required for WEB_SEARCH_PROVIDER={provider_id}"]
    if warning_code == UNSUPPORTED_PROVIDER_WARNING:
        return [
            f"{UNSUPPORTED_PROVIDER_WARNING}: WEB_SEARCH_PROVIDER={provider_id} is recognized but not implemented; "
            "supported live provider: brave"
        ]
    return [warning_code]


def parse_brave_search_response(payload: dict[str, Any]) -> list[WebSearchResult]:
    rows = payload.get("web", {}).get("results", [])
    if not isinstance(rows, list):
        return []
    results: list[WebSearchResult] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = clean_text(row.get("url"))
        if not url:
            continue
        profile = row.get("profile") if isinstance(row.get("profile"), dict) else {}
        results.append(
            WebSearchResult(
                url=url,
                title=clean_text(row.get("title")),
                snippet=clean_text(row.get("description")),
                publisher=clean_text(profile.get("long_name")),
                raw_metadata={
                    key: value
                    for key, value in row.items()
                    if key not in {"url", "title", "description", "profile"}
                },
            )
        )
    return results


def build_search_url(base_url: str, term: str) -> str:
    separator = "&" if parse.urlsplit(base_url).query else "?"
    return f"{base_url}{separator}{parse.urlencode({'q': term})}"


def normalize_url(url: str) -> str:
    parsed = parse.urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return url.strip()
    return parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", parsed.query, ""))


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def infer_publisher(url: str) -> str | None:
    netloc = parse.urlsplit(url).netloc.lower()
    if not netloc:
        return None
    return netloc.removeprefix("www.")


def is_relevant_result(result: WebSearchResult, *, query: str) -> bool:
    normalized_url = normalize_url(result.url)
    parsed = parse.urlsplit(normalized_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    haystack = " ".join(part for part in [result.title, result.snippet, normalized_url, query] if part).casefold()
    if any(term in haystack for term in IRRELEVANT_TERMS):
        return False
    return any(term in haystack for term in POSITIVE_RELEVANCE_TERMS)


def build_notes(source: SourceRegistryEntry, search_term: str, provider_id: str) -> str:
    return (
        f"Discovered by generic web-search pattern source {source.id!r} using provider {provider_id!r} "
        f"for query {search_term!r}. Requires analyst review before candidate extraction."
    )
