from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib import parse

from pydantic import ValidationError

from app.schemas.discovery import DiscoveredSource
from app.services.public_fetch import FetchResult, PublicFetchClient, write_fetch_result
from app.services.source_registry import SourceRegistryEntry


SCC_SEARCH_URL = "https://www.scc.virginia.gov/search/"
SCC_DOCKET_SEARCH_URL = "https://www.scc.virginia.gov/docketsearch/"
SCC_PUBLISHER = "Virginia State Corporation Commission"
VIRGINIA_SCC_SOURCE_ID = "virginia_scc_data_center_large_load_dockets"
RELEVANCE_TERMS = {
    "data center",
    "datacenter",
    "large load",
    "electric service agreement",
    "service agreement",
    "transmission interconnection",
    "interconnection",
    "public utility",
    "case",
    "docket",
}
SCC_URL_MARKERS = {
    "scc.virginia.gov",
    "/docketsearch",
    "/case",
    "/news",
    "/pages",
    "/docs",
    "/document",
    ".pdf",
}


@dataclass
class DiscoveryAdapterResult:
    adapter_id: str
    source_id: str
    planned_queries: list[dict[str, str]] = field(default_factory=list)
    discovered_sources: list[DiscoveredSource] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    fetched_urls: list[str] = field(default_factory=list)
    fetch_results: list[FetchResult] = field(default_factory=list)
    fetch_cache_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "source_id": self.source_id,
            "planned_queries": self.planned_queries,
            "discovered_sources": [source.model_dump(mode="json") for source in self.discovered_sources],
            "warnings": self.warnings,
            "errors": self.errors,
            "fetched_urls": self.fetched_urls,
            "fetch_results": [result.to_dict() for result in self.fetch_results],
            "fetch_cache_paths": self.fetch_cache_paths,
        }


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []
        self._current_href: str | None = None
        self._current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attrs_dict = dict(attrs)
        href = attrs_dict.get("href")
        if href:
            self._current_href = href
            self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._current_href is not None:
            text = data.strip()
            if text:
                self._current_text.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self._current_href is None:
            return
        self.links.append({"href": self._current_href, "title": " ".join(self._current_text).strip()})
        self._current_href = None
        self._current_text = []


@dataclass
class ParsedSearchResult:
    source_url: str
    source_title: str | None
    snippet: str | None
    source_query: str


class SearchResultParser(HTMLParser):
    def __init__(self, *, query: str):
        super().__init__()
        self.query = query
        self.results: list[ParsedSearchResult] = []
        self._in_result = False
        self._result_depth = 0
        self._current_href: str | None = None
        self._current_title: list[str] = []
        self._current_text: list[str] = []
        self._in_anchor = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        class_tokens = set(attrs_dict.get("class", "").lower().split())
        data_attr_names = {name for name, _value in attrs}
        is_result_container = (
            tag in {"li", "article", "div"}
            and (
                {"result", "search-result", "search-result-item"} & class_tokens
                or "data-search-result" in data_attr_names
            )
        )
        if is_result_container and not self._in_result:
            self._in_result = True
            self._result_depth = 1
            self._current_href = None
            self._current_title = []
            self._current_text = []
            self._in_anchor = False
        elif self._in_result:
            self._result_depth += 1

        if tag == "a" and attrs_dict.get("href"):
            if self._in_result:
                self._current_href = attrs_dict["href"]
                self._in_anchor = True

    def handle_data(self, data: str) -> None:
        if not self._in_result:
            return
        text = " ".join(data.split())
        if not text:
            return
        self._current_text.append(text)
        if self._in_anchor:
            self._current_title.append(text)

    def handle_endtag(self, tag: str) -> None:
        if not self._in_result:
            return
        self._result_depth -= 1
        if tag == "a" and self._current_href is not None:
            self._in_anchor = False
        if self._result_depth <= 0:
            self._emit_if_relevant(close_anchor=False)
            self._in_result = False
            self._current_href = None
            self._current_title = []
            self._current_text = []
            self._in_anchor = False

    def _emit_if_relevant(self, *, close_anchor: bool) -> None:
        if self._current_href is None:
            return
        title = " ".join(self._current_title).strip() or None
        snippet = " ".join(self._current_text).strip() or None
        url = parse.urljoin(SCC_SEARCH_URL, self._current_href)
        if is_relevant_scc_result(url=url, title=title, snippet=snippet, query=self.query):
            self.results.append(
                ParsedSearchResult(
                    source_url=url,
                    source_title=title,
                    snippet=snippet,
                    source_query=self.query,
                )
            )
        if close_anchor:
            self._current_href = None
            self._current_title = []
            self._in_anchor = False


class VirginiaSccDiscoveryAdapter:
    adapter_id = "virginia_scc"
    source_id = VIRGINIA_SCC_SOURCE_ID

    def __init__(
        self,
        source: SourceRegistryEntry,
        *,
        fetch_client: PublicFetchClient | None = None,
        fetch_cache_dir: Path | None = None,
    ):
        if source.id != self.source_id:
            raise ValueError(f"Virginia SCC adapter cannot run source {source.id!r}")
        self.source = source
        self.fetch_client = fetch_client or PublicFetchClient()
        self.fetch_cache_dir = fetch_cache_dir

    def run(self, *, dry_run: bool, allow_insecure_fetch: bool = False) -> DiscoveryAdapterResult:
        result = DiscoveryAdapterResult(
            adapter_id=self.adapter_id,
            source_id=self.source.id,
            planned_queries=self.planned_queries(),
        )
        if dry_run:
            result.warnings.append("dry_run_only: Virginia SCC adapter did not fetch public pages")
            return result
        if allow_insecure_fetch and not self.fetch_client.allow_insecure_fetch:
            self.fetch_client = PublicFetchClient(allow_insecure_fetch=True)
        self._probe_public_pages(result)
        return result

    def planned_queries(self) -> list[dict[str, str]]:
        return [
            {
                "term": term,
                "search_url": f"{SCC_SEARCH_URL}?{parse.urlencode({'searchText': term})}",
                "docket_search_url": SCC_DOCKET_SEARCH_URL,
                "action": "probe_scc_public_search_and_docket_pages",
            }
            for term in self.source.search_terms
        ]

    def _probe_public_pages(self, result: DiscoveryAdapterResult) -> None:
        parsed_results: list[ParsedSearchResult] = []
        for query in self.planned_queries():
            fetch_result = self._fetch(query["search_url"], result)
            if not fetch_result.ok or fetch_result.text is None:
                continue
            if "doesn't work properly without JavaScript enabled" in fetch_result.text:
                result.warnings.append(
                    "Virginia SCC search page is JavaScript-rendered; automated result parsing is not reliable yet"
                )
            parsed_results.extend(parse_scc_search_results(fetch_result.text, query=query["term"]))

        discovered = self._sources_from_results(parsed_results)
        if not discovered:
            result.warnings.append("no_parseable_scc_results")
        result.discovered_sources.extend(discovered)

    def _fetch(self, url: str, result: DiscoveryAdapterResult) -> FetchResult:
        fetch_result = self.fetch_client.fetch(url)
        result.fetch_results.append(fetch_result)
        if self.fetch_cache_dir is not None:
            result.fetch_cache_paths.append(str(write_fetch_result(self.fetch_cache_dir, fetch_result)))
        if fetch_result.ok:
            result.fetched_urls.append(fetch_result.final_url or url)
            return fetch_result

        if fetch_result.error_type == "ssl_certificate_error":
            result.warnings.append(
                f"Virginia SCC fetch failed for {url}: ssl_certificate_error; "
                "SSL verification is enabled. Install/update local CA certificates or use "
                "--allow-insecure-fetch for local debugging only."
            )
        else:
            result.warnings.append(
                f"Virginia SCC fetch failed for {url}: {fetch_result.error_type or 'fetch_error'}; "
                f"{fetch_result.error_message or 'no detail'}"
            )
        return fetch_result

    def _extract_relevant_links(self, html: str) -> list[DiscoveredSource]:
        parser = LinkParser()
        parser.feed(html)
        discovered: list[DiscoveredSource] = []
        terms = [term.casefold() for term in self.source.search_terms]
        for link in parser.links:
            href = parse.urljoin(SCC_DOCKET_SEARCH_URL, link["href"])
            title = link["title"] or href
            haystack = f"{title} {href}".casefold()
            if not any(term in haystack for term in terms):
                continue
            try:
                discovered.append(
                    DiscoveredSource(
                        source_url=href,
                        source_title=title,
                        source_type=self.source.source_type,
                        publisher=SCC_PUBLISHER,
                        geography=self.source.geography,
                        discovered_at=datetime.now(timezone.utc),
                        discovery_method=self.source.discovery_method,
                        confidence="candidate_discovered",
                        notes="Parsed from Virginia SCC public docket/search page probe; requires analyst review.",
                    )
                )
            except ValidationError:
                continue
        return discovered

    def _sources_from_results(self, parsed_results: list[ParsedSearchResult]) -> list[DiscoveredSource]:
        discovered: list[DiscoveredSource] = []
        seen_urls: set[str] = set()
        for parsed_result in parsed_results:
            normalized_url = normalize_url(parsed_result.source_url)
            if normalized_url in seen_urls:
                continue
            seen_urls.add(normalized_url)
            try:
                discovered.append(
                    DiscoveredSource(
                        source_url=normalized_url,
                        source_title=parsed_result.source_title,
                        source_type=self.source.source_type,
                        publisher=SCC_PUBLISHER,
                        geography=self.source.geography,
                        discovered_at=datetime.now(timezone.utc),
                        discovery_method=self.source.discovery_method,
                        confidence="candidate_discovered",
                        notes=build_notes(parsed_result),
                        source_query=parsed_result.source_query,
                    )
                )
            except ValidationError:
                continue
        return discovered


def parse_scc_search_results(html: str, *, query: str) -> list[ParsedSearchResult]:
    parser = SearchResultParser(query=query)
    parser.feed(html)
    deduped: dict[str, ParsedSearchResult] = {}
    for result in parser.results:
        deduped.setdefault(normalize_url(result.source_url), result)
    return list(deduped.values())


def normalize_url(url: str) -> str:
    absolute = parse.urljoin(SCC_SEARCH_URL, url)
    parsed = parse.urlsplit(absolute)
    return parse.urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path, parsed.query, ""))


def is_relevant_scc_result(*, url: str, title: str | None, snippet: str | None, query: str) -> bool:
    absolute_url = normalize_url(url)
    if "scc.virginia.gov" not in parse.urlsplit(absolute_url).netloc.lower():
        return False
    url_lower = absolute_url.casefold()
    if not any(marker in url_lower for marker in SCC_URL_MARKERS):
        return False
    haystack = " ".join(part for part in [title, snippet, absolute_url] if part).casefold()
    return any(term in haystack for term in RELEVANCE_TERMS)


def build_notes(result: ParsedSearchResult) -> str:
    parts = [f"Parsed from Virginia SCC public search results for query {result.source_query!r}."]
    if result.snippet:
        parts.append(f"Snippet: {result.snippet[:500]}")
    parts.append("Requires analyst review before candidate extraction.")
    return " ".join(parts)
