from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any
from urllib import parse, request
from urllib.error import HTTPError, URLError

from pydantic import ValidationError

from app.schemas.discovery import DiscoveredSource
from app.services.source_registry import SourceRegistryEntry


USER_AGENT = "data-center-power-risk-public-discovery/0.1"
REQUEST_TIMEOUT_SECONDS = 20
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "source_id": self.source_id,
            "planned_queries": self.planned_queries,
            "discovered_sources": [source.model_dump(mode="json") for source in self.discovered_sources],
            "warnings": self.warnings,
            "errors": self.errors,
            "fetched_urls": self.fetched_urls,
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

    def __init__(self, source: SourceRegistryEntry):
        if source.id != self.source_id:
            raise ValueError(f"Virginia SCC adapter cannot run source {source.id!r}")
        self.source = source

    def run(self, *, dry_run: bool) -> DiscoveryAdapterResult:
        result = DiscoveryAdapterResult(
            adapter_id=self.adapter_id,
            source_id=self.source.id,
            planned_queries=self.planned_queries(),
        )
        if dry_run:
            result.warnings.append("dry_run_only: Virginia SCC adapter did not fetch public pages")
            return result
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
        search_html = self._fetch_text(SCC_SEARCH_URL, result)
        if search_html is None:
            return
        if "doesn't work properly without JavaScript enabled" in search_html:
            result.warnings.append(
                "Virginia SCC search page is JavaScript-rendered; automated result parsing is not reliable yet"
            )

        docket_html = self._fetch_text(SCC_DOCKET_SEARCH_URL, result)
        if docket_html is None:
            return
        discovered = self._extract_relevant_links(docket_html)
        if not discovered:
            result.warnings.append(
                "Virginia SCC docket page probe completed, but no parseable data-center or large-load result links were found"
            )
        result.discovered_sources.extend(discovered)

    def _fetch_text(self, url: str, result: DiscoveryAdapterResult) -> str | None:
        req = request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                content_type = response.headers.get("Content-Type", "")
                raw = response.read(500_000)
        except HTTPError as exc:
            result.warnings.append(f"Virginia SCC fetch failed for {url}: HTTP {exc.code}")
            return None
        except URLError as exc:
            result.warnings.append(f"Virginia SCC fetch failed for {url}: {exc.reason}")
            return None
        except TimeoutError:
            result.warnings.append(f"Virginia SCC fetch timed out for {url}")
            return None

        result.fetched_urls.append(url)
        charset = "utf-8"
        if "charset=" in content_type:
            charset = content_type.rsplit("charset=", 1)[-1].split(";", 1)[0].strip()
        return raw.decode(charset or "utf-8", errors="replace")

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
