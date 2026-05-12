from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, HttpUrl, ValidationError, field_validator


BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent
DEFAULT_REGISTRY_PATH = REPO_DIR / "data" / "source_registry" / "source_registry_v0_1.yaml"

SourceType = Literal[
    "state_regulatory_dockets",
    "utility_large_load_filings",
    "county_city_planning",
    "economic_development_announcements",
    "company_press_releases",
    "developer_websites",
    "data_center_news",
    "grid_context",
]
Priority = Literal["high", "medium", "low"]


class SourceRegistryValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("source registry validation failed: " + "; ".join(errors))


class SourceRegistryEntry(BaseModel):
    id: str
    name: str
    source_type: SourceType
    geography: str
    base_url: HttpUrl
    discovery_method: str
    enabled: bool
    priority: Priority
    search_terms: list[str] = Field(min_length=1)
    notes: str

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("id is required")
        if normalized != normalized.lower() or " " in normalized:
            raise ValueError("id must be lowercase and must not contain spaces")
        return normalized

    @field_validator("name", "geography", "discovery_method", "notes")
    @classmethod
    def require_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("field is required")
        return normalized

    @field_validator("search_terms")
    @classmethod
    def validate_search_terms(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value and value.strip()]
        if not cleaned:
            raise ValueError("search_terms must contain at least one non-empty item")
        return cleaned


class SourceRegistry(BaseModel):
    version: str
    sources: list[SourceRegistryEntry] = Field(min_length=1)

    @field_validator("version")
    @classmethod
    def require_version(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("version is required")
        return normalized

    @field_validator("sources")
    @classmethod
    def validate_unique_ids(cls, sources: list[SourceRegistryEntry]) -> list[SourceRegistryEntry]:
        seen: set[str] = set()
        duplicates: list[str] = []
        for source in sources:
            if source.id in seen:
                duplicates.append(source.id)
            seen.add(source.id)
        if duplicates:
            raise ValueError(f"duplicate source ids: {', '.join(sorted(set(duplicates)))}")
        return sources

    @property
    def enabled_sources(self) -> list[SourceRegistryEntry]:
        return [source for source in self.sources if source.enabled]

    def group_by_source_type(self, *, enabled_only: bool = False) -> dict[str, list[SourceRegistryEntry]]:
        groups: dict[str, list[SourceRegistryEntry]] = defaultdict(list)
        sources = self.enabled_sources if enabled_only else self.sources
        for source in sources:
            groups[source.source_type].append(source)
        return dict(groups)

    @property
    def high_priority_sources(self) -> list[SourceRegistryEntry]:
        return [source for source in self.sources if source.priority == "high"]


def _validation_messages(exc: ValidationError) -> list[str]:
    messages: list[str] = []
    for error in exc.errors():
        loc = ".".join(str(part) for part in error.get("loc", ()))
        msg = error.get("msg", "invalid value")
        messages.append(f"{loc}: {msg}" if loc else msg)
    return messages


def load_source_registry(path: Path = DEFAULT_REGISTRY_PATH) -> SourceRegistry:
    if not path.exists():
        raise SourceRegistryValidationError([f"registry file does not exist: {path}"])
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SourceRegistryValidationError([f"invalid YAML: {exc}"]) from exc

    if not isinstance(raw, dict):
        raise SourceRegistryValidationError(["registry root must be a mapping"])

    try:
        return SourceRegistry.model_validate(raw)
    except ValidationError as exc:
        raise SourceRegistryValidationError(_validation_messages(exc)) from exc


def registry_summary(registry: SourceRegistry) -> dict[str, Any]:
    source_types = sorted(registry.group_by_source_type().keys())
    return {
        "total_sources": len(registry.sources),
        "enabled_sources": len(registry.enabled_sources),
        "source_types": source_types,
        "high_priority_sources": [source.id for source in registry.high_priority_sources],
        "validation_errors": [],
    }
