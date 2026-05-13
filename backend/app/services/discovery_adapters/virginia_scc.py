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
        search_result = self._fetch(SCC_SEARCH_URL, result)
        if not search_result.ok or search_result.text is None:
            return
        search_html = search_result.text
        if "doesn't work properly without JavaScript enabled" in search_html:
            result.warnings.append(
                "Virginia SCC search page is JavaScript-rendered; automated result parsing is not reliable yet"
            )

        docket_result = self._fetch(SCC_DOCKET_SEARCH_URL, result)
        if not docket_result.ok or docket_result.text is None:
            return
        discovered = self._extract_relevant_links(docket_result.text)
        if not discovered:
            result.warnings.append(
                "Virginia SCC docket page probe completed, but no parseable data-center or large-load result links were found"
            )
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
