from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.project_candidate import ProjectCandidate


DUPLICATE_STATUSES = {
    "exact_duplicate",
    "likely_same_project",
    "possible_duplicate",
    "distinct",
    "insufficient_information",
}


@dataclass
class DuplicateMatch:
    record_type: str
    record_id: str | None
    status: str
    reasons: list[str] = field(default_factory=list)
    cluster_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DuplicateDecision:
    status: str
    cluster_key: str | None
    reasons: list[str] = field(default_factory=list)
    matches: list[DuplicateMatch] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "cluster_key": self.cluster_key,
            "reasons": self.reasons,
            "matches": [match.to_dict() for match in self.matches],
        }


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split()).strip()
    return text or None


def normalized_text(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    stopwords = {"llc", "inc", "corp", "corporation", "company", "co", "ltd", "the"}
    words = [word for word in text.split() if word not in stopwords]
    return " ".join(words) or None


def normalized_url(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    parsed = urlsplit(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    netloc = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme.lower()}://{netloc}{path}"


def url_domain(value: str) -> str | None:
    parsed = urlsplit(value)
    return parsed.netloc.lower().removeprefix("www.") or None


def similarity(left: str | None, right: str | None) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def close_coordinates(left_lat: Any, left_lon: Any, right_lat: Any, right_lon: Any) -> bool:
    try:
        lat1, lon1 = float(left_lat), float(left_lon)
        lat2, lon2 = float(right_lat), float(right_lon)
    except (TypeError, ValueError):
        return False
    return abs(lat1 - lat2) <= 0.01 and abs(lon1 - lon2) <= 0.01


def cluster_hash(prefix: str, *parts: Any) -> str:
    normalized = "|".join(normalized_text(part) or "" for part in parts)
    return f"{prefix}:{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:24]}"


class CsvCandidateDedupeService:
    def __init__(self, db: Session | None = None):
        self.db = db

    def evaluate_rows(self, rows: list[dict[str, Any]]) -> list[DuplicateDecision]:
        decisions: list[DuplicateDecision] = []
        prior: list[dict[str, Any]] = []
        for row in rows:
            decision = self.evaluate_row(row, prior_rows=prior)
            decisions.append(decision)
            prior.append(row)
        return decisions

    def evaluate_row(
        self,
        row: dict[str, Any],
        *,
        prior_rows: list[dict[str, Any]] | None = None,
    ) -> DuplicateDecision:
        normalized = row.get("normalized") if isinstance(row.get("normalized"), dict) else row
        matches: list[DuplicateMatch] = []
        for index, prior in enumerate(prior_rows or [], start=1):
            prior_normalized = prior.get("normalized") if isinstance(prior.get("normalized"), dict) else prior
            match = match_normalized_records(normalized, prior_normalized, record_type="imported_row", record_id=str(index))
            if match.status != "distinct":
                matches.append(match)
        if self.db is not None:
            matches.extend(self._candidate_matches(normalized))
            matches.extend(self._project_matches(normalized))

        if not has_minimum_identity(normalized):
            return DuplicateDecision(
                status="insufficient_information",
                cluster_key=None,
                reasons=["missing_project_identity_or_location"],
                matches=matches,
            )

        significant = [match for match in matches if match.status in {"exact_duplicate", "likely_same_project", "possible_duplicate"}]
        if significant:
            order = {"exact_duplicate": 3, "likely_same_project": 2, "possible_duplicate": 1}
            best = max(significant, key=lambda match: order[match.status])
            return DuplicateDecision(
                status=best.status,
                cluster_key=best.cluster_key or default_cluster_key(normalized),
                reasons=best.reasons,
                matches=matches,
            )
        return DuplicateDecision(
            status="distinct",
            cluster_key=default_cluster_key(normalized),
            reasons=["no_conservative_duplicate_signal"],
            matches=matches,
        )

    def _candidate_matches(self, normalized: dict[str, Any]) -> list[DuplicateMatch]:
        assert self.db is not None
        candidates = list(self.db.scalars(select(ProjectCandidate).order_by(ProjectCandidate.created_at.desc()).limit(1000)))
        matches: list[DuplicateMatch] = []
        for candidate in candidates:
            candidate_normalized = {
                "name": candidate.candidate_name,
                "developer": candidate.developer,
                "state": candidate.state,
                "county": candidate.county,
                "address": metadata_value(candidate.raw_metadata_json, "address"),
                "source_urls": [candidate.primary_source_url] if candidate.primary_source_url else [],
                "load_mw": candidate.load_mw,
            }
            match = match_normalized_records(
                normalized,
                candidate_normalized,
                record_type="project_candidate",
                record_id=str(candidate.id),
            )
            if match.status != "distinct":
                matches.append(match)
        return matches

    def _project_matches(self, normalized: dict[str, Any]) -> list[DuplicateMatch]:
        assert self.db is not None
        projects = list(self.db.scalars(select(Project).order_by(Project.created_at.desc()).limit(1000)))
        matches: list[DuplicateMatch] = []
        for project in projects:
            project_normalized = {
                "name": project.canonical_name,
                "developer": project.developer or project.operator,
                "state": project.state,
                "county": project.county,
                "latitude": project.latitude,
                "longitude": project.longitude,
                "source_urls": [],
            }
            match = match_normalized_records(
                normalized,
                project_normalized,
                record_type="project",
                record_id=str(project.id),
            )
            if match.status != "distinct":
                matches.append(match)
        return matches


def metadata_value(metadata: dict | list | None, key: str) -> Any:
    if isinstance(metadata, dict):
        return metadata.get(key)
    return None


def has_minimum_identity(normalized: dict[str, Any]) -> bool:
    name = clean_text(normalized.get("name"))
    state = clean_text(normalized.get("state"))
    address = clean_text(normalized.get("address"))
    lat = normalized.get("latitude")
    lon = normalized.get("longitude")
    return bool(name and (state or address or (lat is not None and lon is not None)))


def default_cluster_key(normalized: dict[str, Any]) -> str | None:
    name = normalized.get("name")
    state = normalized.get("state")
    address = normalized.get("address")
    if name and state:
        return cluster_hash("name_state", name, state)
    if name and address:
        return cluster_hash("name_address", name, address)
    external_id = normalized.get("external_dataset_id")
    dataset = normalized.get("dataset_name")
    if external_id and dataset:
        return cluster_hash("external_id", dataset, external_id)
    return None


def match_normalized_records(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    record_type: str,
    record_id: str | None,
) -> DuplicateMatch:
    reasons: list[str] = []
    left_urls = {normalized_url(url) for url in left.get("source_urls") or []}
    right_urls = {normalized_url(url) for url in right.get("source_urls") or []}
    left_urls.discard(None)
    right_urls.discard(None)
    if left_urls and right_urls and left_urls & right_urls:
        reasons.append("same_source_url")
        return DuplicateMatch(record_type, record_id, "exact_duplicate", reasons, cluster_hash("url", sorted(left_urls & right_urls)[0]))

    if left.get("external_dataset_id") and right.get("external_dataset_id"):
        if normalized_text(left.get("dataset_name")) == normalized_text(right.get("dataset_name")) and clean_text(left.get("external_dataset_id")) == clean_text(right.get("external_dataset_id")):
            reasons.append("same_external_dataset_id")
            return DuplicateMatch(record_type, record_id, "exact_duplicate", reasons, cluster_hash("external_id", left.get("dataset_name"), left.get("external_dataset_id")))

    left_name = normalized_text(left.get("name"))
    right_name = normalized_text(right.get("name"))
    left_state = normalized_text(left.get("state"))
    right_state = normalized_text(right.get("state"))
    left_address = normalized_text(left.get("address"))
    right_address = normalized_text(right.get("address"))
    left_developer = normalized_text(left.get("developer"))
    right_developer = normalized_text(right.get("developer"))

    if left_name and right_name and left_name == right_name and left_state and left_state == right_state:
        reasons.append("same_normalized_name_and_state")
        return DuplicateMatch(record_type, record_id, "likely_same_project", reasons, cluster_hash("name_state", left_name, left_state))
    if left_name and right_name and left_name == right_name and left_address and left_address == right_address:
        reasons.append("same_normalized_name_and_address")
        return DuplicateMatch(record_type, record_id, "likely_same_project", reasons, cluster_hash("name_address", left_name, left_address))
    if left_developer and right_developer and left_developer == right_developer and left_address and left_address == right_address:
        reasons.append("same_developer_and_address")
        return DuplicateMatch(record_type, record_id, "likely_same_project", reasons, cluster_hash("developer_address", left_developer, left_address))
    if close_coordinates(left.get("latitude"), left.get("longitude"), right.get("latitude"), right.get("longitude")):
        reasons.append("very_close_coordinates")
        return DuplicateMatch(record_type, record_id, "likely_same_project", reasons, cluster_hash("coordinates", left.get("latitude"), left.get("longitude")))

    name_score = similarity(left_name, right_name)
    developer_score = similarity(left_developer, right_developer)
    if name_score >= 0.86 and left_state and left_state == right_state:
        reasons.append("fuzzy_name_same_state")
    if developer_score >= 0.88 and left_state and left_state == right_state:
        reasons.append("fuzzy_developer_same_state")
    if left.get("county") and normalized_text(left.get("county")) == normalized_text(right.get("county")) and left_state and left_state == right_state:
        reasons.append("same_county_state")
    if similar_load(left.get("load_mw"), right.get("load_mw")):
        reasons.append("similar_load_mw")
    if shared_source_domain(left_urls, right_urls):
        reasons.append("same_source_domain")
    if left.get("project_family") and normalized_text(left.get("project_family")) == normalized_text(right.get("project_family")):
        reasons.append("same_project_family")

    if len(reasons) >= 2 or (name_score >= 0.92 and (left_state == right_state or left_address or right_address)):
        return DuplicateMatch(record_type, record_id, "possible_duplicate", reasons, default_cluster_key(left))
    return DuplicateMatch(record_type, record_id, "distinct", [], None)


def similar_load(left: Any, right: Any) -> bool:
    try:
        left_value = float(left)
        right_value = float(right)
    except (TypeError, ValueError):
        return False
    tolerance = max(10.0, min(left_value, right_value) * 0.1)
    return abs(left_value - right_value) <= tolerance


def shared_source_domain(left_urls: set[str | None], right_urls: set[str | None]) -> bool:
    left_domains = {url_domain(url) for url in left_urls if url}
    right_domains = {url_domain(url) for url in right_urls if url}
    left_domains.discard(None)
    right_domains.discard(None)
    return bool(left_domains and right_domains and left_domains & right_domains)
