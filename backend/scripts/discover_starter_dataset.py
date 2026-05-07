from __future__ import annotations

import argparse
import csv
import hashlib
import html
import re
import subprocess
import sys
import time
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib import parse, request, robotparser
from urllib.error import HTTPError, URLError


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.enums import ClaimType, SourceType
from app.schemas.automation import IntakePacketRequest
from app.services.automation_service import AutomationService


DEFAULT_SEED_FILE = REPO_DIR / "data" / "starter_sources" / "discovery_seeds.yml"
DEFAULT_RUNTIME_DIR = BACKEND_DIR / "runtime_data" / "starter_sources"
DEFAULT_OUTPUT_CSV = DEFAULT_RUNTIME_DIR / "discovered_sources_v0_1.csv"
DEFAULT_PROJECTS_CSV = REPO_DIR / "data" / "starter_sources" / "projects_v0_1.csv"
USER_AGENT = "data-center-power-risk-starter-discovery/0.1"
MAX_TEXT_CHARS = 12000
REQUEST_TIMEOUT_SECONDS = 20
PDF_TIMEOUT_SECONDS = 30
PDF_MAX_BYTES = 25 * 1024 * 1024
RATE_LIMIT_SECONDS = 1.0

DISCOVERY_COLUMNS = [
    "discovery_id",
    "candidate_project_name",
    "developer",
    "state",
    "county",
    "source_url",
    "source_type",
    "source_date",
    "title",
    "extracted_text",
    "extraction_method",
    "extraction_status",
    "extraction_error",
    "extracted_character_count",
    "detected_load_mw",
    "detected_region",
    "detected_utility",
    "confidence",
    "requires_review_reason",
    "discovery_method",
    "retrieved_at",
]

PROJECT_COLUMNS = [
    "candidate_id",
    "canonical_name",
    "developer",
    "operator",
    "state",
    "county",
    "latitude",
    "longitude",
    "source_url",
    "source_type",
    "source_date",
    "title",
    "evidence_text",
    "known_load_mw",
    "load_note",
    "region_hint",
    "utility_hint",
    "priority_tier",
    "notes",
]


@dataclass
class UrlSeed:
    url: str
    source_type: str | None = None
    project_name: str | None = None
    developer: str | None = None
    state: str | None = None
    county: str | None = None


@dataclass
class ExtractionMeta:
    method: str | None = None
    status: str | None = None
    error: str | None = None
    character_count: int = 0


@dataclass
class FetchResult:
    title: str | None
    text: str | None
    failure_reason: str | None
    extraction: ExtractionMeta


class ReadableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.heading_parts: list[str] = []
        self.text_parts: list[str] = []
        self._skip_depth = 0
        self._in_title = False
        self._in_heading = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag in {"h1", "h2"}:
            self._in_heading = True
        if tag in {"p", "div", "li", "br", "h1", "h2", "h3"}:
            self.text_parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag in {"h1", "h2"}:
            self._in_heading = False
        if tag in {"p", "div", "li", "br", "h1", "h2", "h3"}:
            self.text_parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = html.unescape(data).strip()
        if not text:
            return
        if self._in_title:
            self.title_parts.append(text)
        if self._in_heading:
            self.heading_parts.append(text)
        self.text_parts.append(text)

    @property
    def title(self) -> str | None:
        title = normalize_space(" ".join(self.title_parts)) or normalize_space(" ".join(self.heading_parts))
        return title or None

    @property
    def text(self) -> str:
        return normalize_space(" ".join(self.text_parts))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover reviewable starter dataset source drafts.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and summarize without writing CSV files.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of URL/query seeds to process.")
    parser.add_argument("--seed-file", type=Path, default=DEFAULT_SEED_FILE, help="Discovery seed YAML file.")
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV, help="Discovered sources CSV path.")
    parser.add_argument("--write-projects-csv", action="store_true", help="Write projects_v0_1.csv from high-confidence rows.")
    return parser.parse_args()


def resolve_repo_relative(path: Path) -> Path:
    if path.exists() or path.is_absolute():
        return path
    repo_relative = REPO_DIR / path
    return repo_relative if repo_relative.exists() else path


def resolve_output_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    if path.parts and path.parts[0] == "data":
        return REPO_DIR / path
    return path


def normalize_space(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def parse_scalar(raw: str) -> str | None:
    value = raw.strip()
    if value == "":
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def parse_seed_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Seed file not found: {path}")
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(text)
        if isinstance(loaded, dict):
            return loaded
    except Exception:
        pass
    return parse_simple_yaml(text)


def parse_simple_yaml(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_key: str | None = None
    current_item: dict[str, Any] | None = None
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        if indent == 0 and line.endswith(":"):
            current_key = line[:-1]
            data[current_key] = []
            current_item = None
            continue
        if current_key is None:
            continue
        if line.startswith("- "):
            payload = line[2:]
            if ":" in payload:
                key, value = payload.split(":", 1)
                current_item = {key.strip(): parse_scalar(value)}
                data[current_key].append(current_item)
            else:
                current_item = None
                data[current_key].append(parse_scalar(payload))
            continue
        if current_item is not None and ":" in line:
            key, value = line.split(":", 1)
            current_item[key.strip()] = parse_scalar(value)
    return data


def load_url_seeds(seed_data: dict[str, Any]) -> list[UrlSeed]:
    seeds: list[UrlSeed] = []
    for item in seed_data.get("source_urls", []) or []:
        if not isinstance(item, dict) or not item.get("url"):
            continue
        seeds.append(
            UrlSeed(
                url=str(item["url"]),
                source_type=clean_string(item.get("source_type")),
                project_name=clean_string(item.get("project_name")),
                developer=clean_string(item.get("developer")),
                state=clean_string(item.get("state")),
                county=clean_string(item.get("county")),
            )
        )
    return seeds


def clean_string(value: Any) -> str | None:
    text = normalize_space(str(value)) if value is not None else ""
    return text or None


def robots_url_for(url: str) -> str:
    parsed = parse.urlparse(url)
    return parse.urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))


def can_fetch(url: str) -> tuple[bool, str | None]:
    rp = robotparser.RobotFileParser()
    rp.set_url(robots_url_for(url))
    try:
        rp.read()
    except Exception as exc:
        return True, f"robots_check_failed_allowed_single_seed_fetch: {exc}"
    allowed = rp.can_fetch(USER_AGENT, url)
    return allowed, None if allowed else "blocked_by_robots_txt"


def curl_fetch(url: str) -> tuple[str | None, str | None]:
    try:
        result = subprocess.run(
            [
                "curl",
                "--location",
                "--fail",
                "--silent",
                "--show-error",
                "--max-time",
                str(REQUEST_TIMEOUT_SECONDS),
                "--user-agent",
                USER_AGENT,
                url,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=REQUEST_TIMEOUT_SECONDS + 5,
        )
    except Exception as exc:
        return None, f"curl_fallback_failed: {exc}"
    if result.returncode != 0:
        error = normalize_space(result.stderr) or f"curl exited {result.returncode}"
        return None, f"curl_fallback_failed: {error}"
    return result.stdout, None


def curl_download_pdf(url: str, output_path: Path) -> str | None:
    try:
        result = subprocess.run(
            [
                "curl",
                "--location",
                "--fail",
                "--silent",
                "--show-error",
                "--max-time",
                str(PDF_TIMEOUT_SECONDS),
                "--max-filesize",
                str(PDF_MAX_BYTES),
                "--user-agent",
                USER_AGENT,
                "--output",
                str(output_path),
                url,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=PDF_TIMEOUT_SECONDS + 5,
        )
    except Exception as exc:
        return f"curl_pdf_download_failed: {exc}"
    if result.returncode != 0:
        error = normalize_space(result.stderr) or f"curl exited {result.returncode}"
        return f"curl_pdf_download_failed: {error}"
    return None


def parse_html_text(html_text: str) -> tuple[str | None, str | None]:
    parser = ReadableHTMLParser()
    parser.feed(html_text)
    text = parser.text[:MAX_TEXT_CHARS]
    return parser.title, text or None


def pdf_title_from_url(url: str) -> str:
    filename = Path(parse.urlparse(url).path).name
    return parse.unquote(filename) or "PDF source"


def download_pdf(url: str, output_path: Path) -> str | None:
    req = request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/pdf,*/*;q=0.1"})
    downloaded = 0
    try:
        with request.urlopen(req, timeout=PDF_TIMEOUT_SECONDS) as response:
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > PDF_MAX_BYTES:
                return f"pdf_too_large: content_length={content_length}"
            with output_path.open("wb") as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    downloaded += len(chunk)
                    if downloaded > PDF_MAX_BYTES:
                        return f"pdf_too_large: downloaded>{PDF_MAX_BYTES}"
                    handle.write(chunk)
    except HTTPError as exc:
        return f"pdf_download_failed_http_{exc.code}"
    except URLError as exc:
        if "CERTIFICATE_VERIFY_FAILED" in str(exc.reason):
            fallback_error = curl_download_pdf(url, output_path)
            if fallback_error:
                return f"pdf_download_failed_url_error: {exc.reason}; {fallback_error}"
            return None
        return f"pdf_download_failed_url_error: {exc.reason}"
    except TimeoutError:
        return "pdf_download_failed_timeout"
    except Exception as exc:
        return f"pdf_download_failed: {exc}"
    return None


def extract_pdf_with_pypdf(path: Path) -> tuple[str | None, str | None]:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception as exc:
        return None, f"pypdf_unavailable: {exc}"
    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            return None, "pdf_encrypted_skipped"
        parts: list[str] = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
            if sum(len(part) for part in parts) >= MAX_TEXT_CHARS:
                break
        text = normalize_space(" ".join(parts))[:MAX_TEXT_CHARS]
        if not text:
            return None, "pdf_no_extractable_text"
        return text, None
    except Exception as exc:
        return None, f"pypdf_extract_failed: {exc}"


def extract_pdf_with_pdfplumber(path: Path) -> tuple[str | None, str | None]:
    try:
        import pdfplumber  # type: ignore
    except Exception as exc:
        return None, f"pdfplumber_unavailable: {exc}"
    try:
        parts: list[str] = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                parts.append(page.extract_text() or "")
                if sum(len(part) for part in parts) >= MAX_TEXT_CHARS:
                    break
        text = normalize_space(" ".join(parts))[:MAX_TEXT_CHARS]
        if not text:
            return None, "pdf_no_extractable_text"
        return text, None
    except Exception as exc:
        return None, f"pdfplumber_extract_failed: {exc}"


def fetch_pdf_url(url: str, robots_note: str | None) -> FetchResult:
    title = pdf_title_from_url(url)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as handle:
        pdf_path = Path(handle.name)
        error = download_pdf(url, pdf_path)
        if error:
            print(f"[pdf] failed {url} {error}", file=sys.stderr)
            return FetchResult(
                title=title,
                text=None,
                failure_reason=append_reason(robots_note, error),
                extraction=ExtractionMeta(method="pdf_text", status="failed", error=error),
            )
        size = pdf_path.stat().st_size
        if size > PDF_MAX_BYTES:
            error = f"pdf_too_large: downloaded={size}"
            print(f"[pdf] failed {url} {error}", file=sys.stderr)
            return FetchResult(title=title, text=None, failure_reason=append_reason(robots_note, error), extraction=ExtractionMeta(method="pdf_text", status="failed", error=error))
        print(f"[pdf] downloaded {url} bytes={size}", file=sys.stderr)

        text, error = extract_pdf_with_pypdf(pdf_path)
        if text is None and error and not error.startswith("pdf_encrypted_skipped"):
            fallback_text, fallback_error = extract_pdf_with_pdfplumber(pdf_path)
            if fallback_text is not None:
                text, error = fallback_text, None
            elif fallback_error:
                error = f"{error}; {fallback_error}"
        if text is None:
            final_error = error or "pdf_extract_failed"
            print(f"[pdf] failed {url} {final_error}", file=sys.stderr)
            return FetchResult(
                title=title,
                text=None,
                failure_reason=append_reason(robots_note, final_error),
                extraction=ExtractionMeta(method="pdf_text", status="failed", error=final_error),
            )
        print(f"[pdf] extracted {url} chars={len(text)}", file=sys.stderr)
        return FetchResult(
            title=title,
            text=text,
            failure_reason=robots_note,
            extraction=ExtractionMeta(method="pdf_text", status="succeeded", character_count=len(text)),
        )


def fetch_url(url: str) -> FetchResult:
    allowed, robots_note = can_fetch(url)
    if not allowed:
        return FetchResult(None, None, robots_note, ExtractionMeta(method=None, status="failed", error=robots_note))
    parsed = parse.urlparse(url)
    if parsed.path.lower().endswith(".pdf"):
        return fetch_pdf_url(url, robots_note)
    req = request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/plain;q=0.9,*/*;q=0.1"})
    try:
        with request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            content_type = response.headers.get("content-type", "")
            raw = response.read(2_000_000)
    except HTTPError as exc:
        error = f"fetch_failed_http_{exc.code}"
        return FetchResult(None, None, error, ExtractionMeta(method="html_text", status="failed", error=error))
    except URLError as exc:
        if "CERTIFICATE_VERIFY_FAILED" in str(exc.reason):
            html_text, curl_error = curl_fetch(url)
            if curl_error:
                error = f"fetch_failed_url_error: {exc.reason}; {curl_error}"
                return FetchResult(None, None, error, ExtractionMeta(method="html_text", status="failed", error=error))
            title, text = parse_html_text(html_text or "")
            if not text:
                error = "no_readable_text_extracted_after_curl_tls_fallback"
                return FetchResult(title, None, error, ExtractionMeta(method="html_text", status="failed", error=error))
            return FetchResult(title, text, append_reason(robots_note, "urllib_tls_failed_curl_fallback_used"), ExtractionMeta(method="html_text", status="succeeded", character_count=len(text)))
        error = f"fetch_failed_url_error: {exc.reason}"
        return FetchResult(None, None, error, ExtractionMeta(method="html_text", status="failed", error=error))
    except TimeoutError:
        return FetchResult(None, None, "fetch_failed_timeout", ExtractionMeta(method="html_text", status="failed", error="fetch_failed_timeout"))
    except Exception as exc:
        error = f"fetch_failed: {exc}"
        return FetchResult(None, None, error, ExtractionMeta(method="html_text", status="failed", error=error))

    if "pdf" in content_type.lower():
        return fetch_pdf_url(url, robots_note)
    encoding = "utf-8"
    match = re.search(r"charset=([\w.-]+)", content_type, re.IGNORECASE)
    if match:
        encoding = match.group(1)
    html_text = raw.decode(encoding, errors="replace")
    title, text = parse_html_text(html_text)
    if not text:
        error = "no_readable_text_extracted"
        return FetchResult(title, None, error, ExtractionMeta(method="html_text", status="failed", error=error))
    return FetchResult(title, text, robots_note, ExtractionMeta(method="html_text", status="succeeded", character_count=len(text)))


def append_reason(existing: str | None, extra: str) -> str:
    return f"{existing}; {extra}" if existing else extra


def detect_date(text: str, seed_url: str) -> str | None:
    iso_match = re.search(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", text)
    if iso_match:
        year, month, day = iso_match.groups()
        try:
            return date(int(year), int(month), int(day)).isoformat()
        except ValueError:
            pass
    month_names = "January|February|March|April|May|June|July|August|September|October|November|December|Jan\\.?|Feb\\.?|Mar\\.?|Apr\\.?|Jun\\.?|Jul\\.?|Aug\\.?|Sep\\.?|Sept\\.?|Oct\\.?|Nov\\.?|Dec\\.?"
    match = re.search(rf"\b({month_names})\s+(\d{{1,2}}),?\s+(20\d{{2}})\b", text, re.IGNORECASE)
    if match:
        month_raw, day, year = match.groups()
        month_key = month_raw.lower().rstrip(".")[:3]
        month_num = {
            "jan": 1,
            "feb": 2,
            "mar": 3,
            "apr": 4,
            "may": 5,
            "jun": 6,
            "jul": 7,
            "aug": 8,
            "sep": 9,
            "oct": 10,
            "nov": 11,
            "dec": 12,
        }[month_key]
        try:
            return date(int(year), month_num, int(day)).isoformat()
        except ValueError:
            pass
    year_match = re.search(r"/(20\d{2})/(\d{2})/", seed_url)
    if year_match:
        year, month = year_match.groups()
        return f"{year}-{month}-01"
    return None


def extract_claim_values(text: str, source_type: SourceType) -> dict[str, Any]:
    values: dict[str, Any] = {}
    packet = AutomationService().build_intake_packet(
        IntakePacketRequest(
            source_type=source_type,
            source_date=None,
            source_url=None,
            title=None,
            evidence_text=text,
            project_id=None,
        )
    )
    for claim in packet.claims_payload.claims:
        claim_value = claim.claim_value.model_dump()
        if claim.claim_type == ClaimType.PROJECT_NAME_MENTION and "candidate_project_name" not in values:
            values["candidate_project_name"] = claim_value.get("project_name")
        elif claim.claim_type == ClaimType.DEVELOPER_NAMED and "developer" not in values:
            values["developer"] = claim_value.get("developer_name")
        elif claim.claim_type == ClaimType.LOCATION_STATE and "state" not in values:
            values["state"] = claim_value.get("state")
        elif claim.claim_type == ClaimType.LOCATION_COUNTY and "county" not in values:
            values["county"] = claim_value.get("county")
        elif claim.claim_type == ClaimType.MODELED_LOAD_MW and "detected_load_mw" not in values:
            values["detected_load_mw"] = claim_value.get("modeled_primary_load_mw")
        elif claim.claim_type == ClaimType.OPTIONAL_EXPANSION_MW and "detected_load_mw" not in values:
            values["detected_load_mw"] = claim_value.get("optional_expansion_mw")
        elif claim.claim_type == ClaimType.REGION_OR_RTO_NAMED and "detected_region" not in values:
            values["detected_region"] = claim_value.get("region_name")
        elif claim.claim_type == ClaimType.UTILITY_NAMED and "detected_utility" not in values:
            values["detected_utility"] = claim_value.get("utility_name")
    if "detected_load_mw" not in values:
        load_match = re.search(
            r"(?<![\d,])(\d{1,3}(?:,\d{3})+|\d{2,5}(?:\.\d+)?)\s*(?:MW|megawatts?)\b",
            text,
            re.IGNORECASE,
        )
        if load_match:
            values["detected_load_mw"] = load_match.group(1).replace(",", "")
    return values


def coerce_source_type(value: str | None, url: str) -> SourceType:
    if value:
        try:
            return SourceType(value)
        except ValueError:
            pass
    lowered = url.lower()
    if "ercot.com" in lowered or "nerc.com" in lowered or "pjm.com" in lowered or "puc" in lowered:
        return SourceType.REGULATORY_RECORD
    if "entergy" in lowered or "dominion" in lowered:
        return SourceType.UTILITY_STATEMENT
    if "prnewswire" in lowered:
        return SourceType.PRESS
    return SourceType.OTHER


def confidence_for(row: dict[str, Any], failure_reason: str | None) -> str:
    if failure_reason and not row.get("extracted_text"):
        return "low"
    signals = sum(bool(row.get(key)) for key in ["candidate_project_name", "developer", "state", "county", "detected_load_mw"])
    if signals >= 4:
        return "high"
    if signals >= 2:
        return "medium"
    return "low"


def review_reason_for(row: dict[str, Any], failure_reason: str | None) -> str:
    reasons: list[str] = []
    if failure_reason:
        reasons.append(failure_reason)
    if not row.get("candidate_project_name"):
        reasons.append("candidate_project_name_requires_review")
    if row.get("detected_load_mw"):
        reasons.append("detected_load_not_auto_accepted")
    else:
        reasons.append("load_not_detected")
    if row.get("detected_region"):
        reasons.append("region_not_auto_accepted")
    if row.get("detected_utility"):
        reasons.append("utility_not_auto_accepted")
    reasons.append("analyst_review_required_before_ingest")
    return "; ".join(dict.fromkeys(reasons))


def discovery_id_for(url_or_query: str) -> str:
    return "DISC_" + hashlib.sha1(url_or_query.encode("utf-8")).hexdigest()[:12].upper()


def discover_url(seed: UrlSeed, retrieved_at: str) -> dict[str, Any]:
    source_type = coerce_source_type(seed.source_type, seed.url)
    fetched = fetch_url(seed.url)
    evidence_text = fetched.text or ""
    claim_values = extract_claim_values(evidence_text, source_type) if evidence_text else {}
    source_date = detect_date(" ".join(part for part in [fetched.title or "", evidence_text[:3000]] if part), seed.url)
    row: dict[str, Any] = {
        "discovery_id": discovery_id_for(seed.url),
        "candidate_project_name": seed.project_name or claim_values.get("candidate_project_name"),
        "developer": seed.developer or claim_values.get("developer"),
        "state": seed.state or claim_values.get("state"),
        "county": seed.county or claim_values.get("county"),
        "source_url": seed.url,
        "source_type": source_type.value,
        "source_date": source_date,
        "title": fetched.title,
        "extracted_text": evidence_text,
        "extraction_method": fetched.extraction.method,
        "extraction_status": fetched.extraction.status,
        "extraction_error": fetched.extraction.error,
        "extracted_character_count": fetched.extraction.character_count,
        "detected_load_mw": claim_values.get("detected_load_mw"),
        "detected_region": claim_values.get("detected_region"),
        "detected_utility": claim_values.get("detected_utility"),
        "confidence": None,
        "requires_review_reason": None,
        "discovery_method": "url_seed",
        "retrieved_at": retrieved_at,
    }
    row["confidence"] = confidence_for(row, fetched.failure_reason)
    row["requires_review_reason"] = review_reason_for(row, fetched.failure_reason)
    return {column: clean_string(row.get(column)) for column in DISCOVERY_COLUMNS}


def query_seed_row(query: str, retrieved_at: str) -> dict[str, Any]:
    row = {
        "discovery_id": discovery_id_for(f"query:{query}"),
        "candidate_project_name": None,
        "developer": None,
        "state": None,
        "county": None,
        "source_url": f"query:{query}",
        "source_type": SourceType.OTHER.value,
        "source_date": None,
        "title": query,
        "extracted_text": "",
        "extraction_method": None,
        "extraction_status": "not_fetched",
        "extraction_error": "query_seed_not_fetched",
        "extracted_character_count": 0,
        "detected_load_mw": None,
        "detected_region": None,
        "detected_utility": None,
        "confidence": "low",
        "requires_review_reason": "query_seed_not_fetched; add reviewed source URLs before ingest; analyst_review_required_before_ingest",
        "discovery_method": "query_seed",
        "retrieved_at": retrieved_at,
    }
    return {column: clean_string(row.get(column)) for column in DISCOVERY_COLUMNS}


def write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column) for column in columns})


def project_row_from_discovery(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": row["discovery_id"],
        "canonical_name": row["candidate_project_name"],
        "developer": row["developer"],
        "operator": "",
        "state": row["state"],
        "county": row["county"],
        "latitude": "",
        "longitude": "",
        "source_url": row["source_url"],
        "source_type": row["source_type"],
        "source_date": row["source_date"],
        "title": row["title"],
        "evidence_text": row["extracted_text"],
        "known_load_mw": row["detected_load_mw"],
        "load_note": "discovered_load_requires_review" if row.get("detected_load_mw") else "",
        "region_hint": row["detected_region"],
        "utility_hint": row["detected_utility"],
        "priority_tier": "A" if row["confidence"] == "high" else "B",
        "notes": f"Generated from discovery row {row['discovery_id']}; analyst review required.",
    }


def main() -> None:
    args = parse_args()
    if args.limit is not None and args.limit < 0:
        raise SystemExit("--limit must be non-negative.")
    args.seed_file = resolve_repo_relative(args.seed_file)
    args.output_csv = resolve_output_path(args.output_csv)
    seed_data = parse_seed_file(args.seed_file)
    url_seeds = load_url_seeds(seed_data)
    query_seeds = [str(item) for item in seed_data.get("search_query_seeds", []) or [] if item]

    retrieved_at = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []
    processed = 0
    for seed in url_seeds:
        if args.limit is not None and processed >= args.limit:
            break
        rows.append(discover_url(seed, retrieved_at))
        processed += 1
        if args.limit is None or processed < args.limit:
            time.sleep(RATE_LIMIT_SECONDS)
    for query in query_seeds:
        if args.limit is not None and processed >= args.limit:
            break
        rows.append(query_seed_row(query, retrieved_at))
        processed += 1

    high_confidence_rows = [
        row
        for row in rows
        if row.get("confidence") == "high"
        and row.get("source_url", "").startswith(("http://", "https://"))
        and row.get("candidate_project_name")
        and row.get("extracted_text")
    ]

    if not args.dry_run:
        write_csv(args.output_csv, DISCOVERY_COLUMNS, rows)
        if args.write_projects_csv:
            write_csv(DEFAULT_PROJECTS_CSV, PROJECT_COLUMNS, [project_row_from_discovery(row) for row in high_confidence_rows])

    failure_count = sum(1 for row in rows if "fetch_failed" in (row.get("requires_review_reason") or "") or "blocked_by_robots" in (row.get("requires_review_reason") or "") or "not_supported" in (row.get("requires_review_reason") or ""))
    print(
        "\n".join(
            [
                f"discovered_rows={len(rows)}",
                f"high_confidence_rows={len(high_confidence_rows)}",
                f"failure_or_unfetched_rows={failure_count + sum(1 for row in rows if row.get('discovery_method') == 'query_seed')}",
                f"output_csv={'not_written_dry_run' if args.dry_run else args.output_csv}",
                f"projects_csv={'not_written' if args.dry_run or not args.write_projects_csv else DEFAULT_PROJECTS_CSV}",
            ]
        )
    )
    for row in rows[:20]:
        print(
            f"{row['discovery_id']} | {row['confidence']} | {row['discovery_method']} | "
            f"{row.get('candidate_project_name') or '(review project)'} | {row['source_url']}"
        )


if __name__ == "__main__":
    main()
