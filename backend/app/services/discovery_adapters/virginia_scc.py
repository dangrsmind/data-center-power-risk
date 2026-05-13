from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import unescape
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
SEARCHSTAX_DISCOVERY_METHOD = "searchstax_query"
SEARCHSTAX_ROWS = 10
SEARCHSTAX_TABS = {
    "all": "all",
    "site_pages": "type_s:web page",
    "news": "sectionType_s:news",
    "cases": "sectionType_s:case",
    "pdfs": "type_s:pdf",
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
    source_type: str | None = None
    case_number: str | None = None
    document_type: str | None = None


@dataclass
class SearchStaxConfig:
    connector_url: str
    apikey: str | None
    select_auth_token: str
    suggester_url: str | None
    suggester_auth_token: str | None
    search_auth_type: str
    search_api_key: str | None
    language: str
    search_additional_args: str | None
    script_urls: list[str]
    stylesheet_urls: list[str]
    tabs: dict[str, str]

    @property
    def requires_browser_execution(self) -> bool:
        return not self.connector_url or not self.select_auth_token or self.search_auth_type != "token"


class SearchStaxShellParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.script_urls: list[str] = []
        self.stylesheet_urls: list[str] = []
        self.tabs: dict[str, str] = {}
        self.script_blocks: list[str] = []
        self._in_script = False
        self._script_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "script":
            src = attrs_dict.get("src")
            if src:
                self.script_urls.append(parse.urljoin(SCC_SEARCH_URL, src))
            self._in_script = src is None
            self._script_parts = []
        elif tag == "link":
            href = attrs_dict.get("href")
            rel = (attrs_dict.get("rel") or "").casefold()
            if href and ("stylesheet" in rel or "preload" in rel):
                self.stylesheet_urls.append(parse.urljoin(SCC_SEARCH_URL, href))
        elif tag == "button":
            facet_id = attrs_dict.get("facet-id")
            button_id = attrs_dict.get("id")
            if facet_id and button_id:
                self.tabs[button_id] = facet_id

    def handle_data(self, data: str) -> None:
        if self._in_script:
            self._script_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_script:
            self.script_blocks.append("".join(self._script_parts))
            self._script_parts = []
            self._in_script = False


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


class SccSearchStaxClient:
    def __init__(self, *, config: SearchStaxConfig, fetch_client: PublicFetchClient):
        self.config = config
        self.fetch_client = fetch_client

    def query(self, term: str, *, tab: str = "all", rows: int = SEARCHSTAX_ROWS) -> FetchResult:
        params: dict[str, str] = {
            "q": term,
            "rows": str(rows),
            "start": "0",
            "spellcheck.correct": "false",
            "language": self.config.language,
        }
        if self.config.search_additional_args:
            params.update(parse.parse_qsl(self.config.search_additional_args, keep_blank_values=True))
        facet = SEARCHSTAX_TABS.get(tab)
        if facet and facet != "all":
            params["fq"] = facet
        url = f"{self.config.connector_url}?{parse.urlencode(params)}"
        return self.fetch_client.fetch(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Token {self.config.select_auth_token}",
            },
        )


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
                "search_url": f"{SCC_SEARCH_URL}?{parse.urlencode({'searchStudioQuery': term})}",
                "docket_search_url": SCC_DOCKET_SEARCH_URL,
                "action": "query_scc_searchstax_public_search",
            }
            for term in self.source.search_terms
        ]

    def _probe_public_pages(self, result: DiscoveryAdapterResult) -> None:
        shell_fetch = self._fetch(SCC_SEARCH_URL, result)
        if not shell_fetch.ok or shell_fetch.text is None:
            result.warnings.append("scc_search_requires_client_side_execution")
            return
        config = extract_searchstax_config(shell_fetch.text)
        if config is None:
            result.warnings.append("scc_search_requires_client_side_execution")
            result.warnings.append(
                "Virginia SCC search page is client-rendered and no stable SearchStax connector config was found"
            )
            return
        result.warnings.append(
            "Virginia SCC static search page is client-rendered; using public SearchStax connector config"
        )
        if config.requires_browser_execution:
            result.warnings.append("scc_search_requires_client_side_execution")
            result.warnings.append(
                "Virginia SCC SearchStax config requires dynamic browser execution or unsupported authentication"
            )
            return

        client = SccSearchStaxClient(config=config, fetch_client=self.fetch_client)
        parsed_results: list[ParsedSearchResult] = []
        for query in self.planned_queries():
            fetch_result = self._fetch_searchstax_query(client, query["term"], result)
            if not fetch_result.ok or fetch_result.text is None:
                continue
            parsed_results.extend(parse_searchstax_response(fetch_result.text, query=query["term"]))

        discovered = self._sources_from_results(parsed_results)
        if not discovered:
            result.warnings.append("no_scc_searchstax_results")
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

    def _fetch_searchstax_query(
        self,
        client: SccSearchStaxClient,
        term: str,
        result: DiscoveryAdapterResult,
    ) -> FetchResult:
        fetch_result = client.query(term)
        result.fetch_results.append(fetch_result)
        if self.fetch_cache_dir is not None:
            result.fetch_cache_paths.append(str(write_fetch_result(self.fetch_cache_dir, fetch_result)))
        if fetch_result.ok:
            result.fetched_urls.append(fetch_result.final_url or fetch_result.url)
            return fetch_result
        result.warnings.append(
            f"Virginia SCC SearchStax query failed for {term!r}: "
            f"{fetch_result.error_type or 'fetch_error'}; {fetch_result.error_message or 'no detail'}"
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
                        discovery_method=SEARCHSTAX_DISCOVERY_METHOD,
                        confidence="candidate_discovered",
                        notes=build_notes(parsed_result),
                        source_query=parsed_result.source_query,
                        snippet=parsed_result.snippet,
                        case_number=parsed_result.case_number,
                        document_type=parsed_result.document_type or parsed_result.source_type,
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


def extract_searchstax_config(html: str) -> SearchStaxConfig | None:
    parser = SearchStaxShellParser()
    parser.feed(html)
    config_script = next((script for script in parser.script_blocks if "const studioConfig" in script), None)
    if config_script is None:
        return None
    connector_block = _extract_js_object_block(config_script, "connector")
    if connector_block is None:
        return None

    connector_url = _extract_js_string(connector_block, "url")
    select_auth_token = _extract_js_string(connector_block, "select_auth_token")
    if not connector_url or not select_auth_token:
        return None
    search_additional_args = _extract_js_string(connector_block, "searchAdditionalArgs")
    return SearchStaxConfig(
        connector_url=connector_url,
        apikey=_extract_js_string(connector_block, "apikey"),
        select_auth_token=select_auth_token,
        suggester_url=_extract_js_string(connector_block, "suggester"),
        suggester_auth_token=_extract_js_string(connector_block, "suggester_auth_token"),
        search_auth_type=_extract_js_string(connector_block, "search_auth_type") or "",
        search_api_key=_extract_js_string(connector_block, "searchAPIKey"),
        language=_extract_js_string(connector_block, "language") or "en",
        search_additional_args=search_additional_args,
        script_urls=parser.script_urls,
        stylesheet_urls=parser.stylesheet_urls,
        tabs=parser.tabs,
    )


def parse_searchstax_response(payload: str | dict[str, Any], *, query: str) -> list[ParsedSearchResult]:
    data = json.loads(payload) if isinstance(payload, str) else payload
    docs = data.get("response", {}).get("docs", [])
    highlighting = data.get("highlighting", {})
    parsed_results: list[ParsedSearchResult] = []
    if not isinstance(docs, list):
        return parsed_results
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        source_url = _first_text(doc.get("url")) or _first_text(doc.get("id"))
        if not source_url:
            continue
        title = _first_text(doc.get("dctitle_t")) or _first_text(doc.get("LongName_txt_en"))
        title = title or _first_text(doc.get("DocumentName_t")) or source_url
        doc_id = _first_text(doc.get("id")) or source_url
        snippet = _snippet_from_highlighting(highlighting.get(doc_id)) or _first_text(doc.get("content"))
        case_number = _case_number(doc)
        document_type = _first_text(doc.get("DocumentType_s")) or _first_text(doc.get("sectionType_s"))
        source_type = _first_text(doc.get("type_s"))
        if not is_relevant_scc_result(url=source_url, title=title, snippet=snippet, query=query):
            continue
        parsed_results.append(
            ParsedSearchResult(
                source_url=source_url,
                source_title=clean_text(title),
                snippet=clean_text(snippet, limit=500),
                source_query=query,
                source_type=source_type,
                case_number=case_number,
                document_type=document_type,
            )
        )
    deduped: dict[str, ParsedSearchResult] = {}
    for result in parsed_results:
        deduped.setdefault(normalize_url(result.source_url), result)
    return list(deduped.values())


def _extract_js_object_block(script: str, key: str) -> str | None:
    match = re.search(rf"\b{re.escape(key)}\s*:\s*\{{", script)
    if match is None:
        return None
    start = match.end() - 1
    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(start, len(script)):
        char = script[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return script[start : index + 1]
    return None


def _extract_js_string(block: str, key: str) -> str | None:
    match = re.search(rf"\b{re.escape(key)}\s*:\s*([\"'])(.*?)\1", block, flags=re.DOTALL)
    if match is None:
        return None
    return bytes(match.group(2), "utf-8").decode("unicode_escape")


def _first_text(value: Any) -> str | None:
    if isinstance(value, list):
        for item in value:
            text = _first_text(item)
            if text:
                return text
        return None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _snippet_from_highlighting(highlight_doc: Any) -> str | None:
    if not isinstance(highlight_doc, dict):
        return None
    for field_name in ("content", "dctitle_t", "LongName_txt_en", "MetaDescription_txt_en", "url"):
        text = _first_text(highlight_doc.get(field_name))
        if text:
            return text
    return None


def _case_number(doc: dict[str, Any]) -> str | None:
    prefix = _first_text(doc.get("CaseNumberPrefix_t"))
    number = _first_text(doc.get("CaseNumberCaseNumber_t"))
    if prefix and number:
        return f"{prefix}-{number}"
    return number


def clean_text(value: str | None, *, limit: int | None = None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"<[^>]+>", "", unescape(value))
    cleaned = " ".join(cleaned.split())
    if limit is not None:
        return cleaned[:limit]
    return cleaned or None


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
    parts = [f"Parsed from Virginia SCC public SearchStax results for query {result.source_query!r}."]
    if result.case_number:
        parts.append(f"Case number: {result.case_number}.")
    if result.document_type or result.source_type:
        parts.append(f"Document/type: {result.document_type or result.source_type}.")
    if result.snippet:
        parts.append(f"Snippet: {result.snippet[:500]}")
    parts.append("Requires analyst review before candidate extraction.")
    return " ".join(parts)
