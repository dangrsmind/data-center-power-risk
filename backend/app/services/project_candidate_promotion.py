from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import timezone, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import ClaimEntityType, LifecycleState, ReviewerStatus, SourceType
from app.models.evidence import Evidence, FieldProvenance
from app.models.project import Project
from app.models.project_candidate import ProjectCandidate


PROMOTION_REVIEWER = "project_candidate_promotion"
UNRESOLVED_NAME_PREFIX = "Unresolved "


@dataclass
class ProjectCandidatePromotionSummary:
    dry_run: bool
    candidate_id: str
    promoted: bool = False
    project_created: bool = False
    project_updated: bool = False
    would_promote: bool = False
    would_create_project: bool = False
    would_update_project: bool = False
    evidence_created: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    promoted_project_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProjectCandidatePromotionService:
    def __init__(self, db: Session):
        self.db = db

    def promote(
        self,
        candidate_id: uuid.UUID,
        *,
        confirm: bool = False,
        allow_unresolved_name: bool = False,
        allow_incomplete: bool = False,
    ) -> ProjectCandidatePromotionSummary:
        summary = ProjectCandidatePromotionSummary(dry_run=not confirm, candidate_id=str(candidate_id))
        candidate = self.db.get(ProjectCandidate, candidate_id)
        if candidate is None:
            summary.errors.append("candidate_not_found")
            return summary

        errors = validate_candidate_for_promotion(
            candidate,
            allow_unresolved_name=allow_unresolved_name,
            allow_incomplete=allow_incomplete,
        )
        if errors:
            summary.errors.extend(errors)
            return summary

        if candidate.promoted_project_id:
            project = self.db.get(Project, candidate.promoted_project_id)
            if project is None:
                summary.errors.append("promoted_project_missing")
                return summary
            if confirm and candidate.status != "promoted":
                candidate.status = "promoted"
                summary.warnings.append("candidate_status_corrected")
                self.db.flush()
            elif candidate.status != "promoted":
                summary.warnings.append("candidate_status_would_be_corrected")
            summary.promoted = True
            summary.promoted_project_id = str(project.id)
            summary.warnings.append("candidate_already_promoted")
            return summary

        existing_project = self._find_existing_project(candidate)
        if not confirm:
            summary.would_promote = True
            summary.would_create_project = existing_project is None
            summary.would_update_project = existing_project is not None
            summary.promoted_project_id = str(existing_project.id) if existing_project else None
            summary.warnings.extend(mapping_warnings(candidate))
            summary.warnings.append("dry_run_only_no_records_written")
            return summary

        project = existing_project
        if project is None:
            project = build_project(candidate)
            self.db.add(project)
            self.db.flush()
            summary.project_created = True
        else:
            update_project_from_candidate(project, candidate)
            summary.project_updated = True

        evidence = self._find_existing_evidence(project.id, candidate)
        if evidence is None:
            evidence = build_evidence(candidate)
            self.db.add(evidence)
            self.db.flush()
            self.db.add(
                FieldProvenance(
                    entity_type=ClaimEntityType.PROJECT,
                    entity_id=project.id,
                    field_name="project_candidate_promotion",
                    evidence_id=evidence.id,
                    claim_id=None,
                )
            )
            summary.evidence_created = 1

        candidate.status = "promoted"
        candidate.promoted_project_id = project.id
        candidate.raw_metadata_json = with_promotion_metadata(candidate.raw_metadata_json, project.id, evidence.id)
        summary.promoted = True
        summary.promoted_project_id = str(project.id)
        summary.warnings.extend(mapping_warnings(candidate))
        self.db.flush()
        return summary

    def _find_existing_project(self, candidate: ProjectCandidate) -> Project | None:
        if candidate.promoted_project_id:
            project = self.db.get(Project, candidate.promoted_project_id)
            if project is not None:
                return project
        projects = self.db.scalars(select(Project)).all()
        for project in projects:
            metadata = project.candidate_metadata_json
            if isinstance(metadata, dict) and metadata.get("project_candidate_id") == str(candidate.id):
                return project
        state = normalize_state(candidate.state)
        if candidate.primary_source_url:
            for project in projects:
                metadata = project.candidate_metadata_json
                if not isinstance(metadata, dict):
                    continue
                if (
                    project.canonical_name == candidate.candidate_name
                    and project.state == state
                    and metadata.get("primary_source_url") == candidate.primary_source_url
                ):
                    return project
        return None

    def _find_existing_evidence(self, project_id: uuid.UUID, candidate: ProjectCandidate) -> Evidence | None:
        rows = self.db.execute(
            select(Evidence)
            .join(FieldProvenance, FieldProvenance.evidence_id == Evidence.id)
            .where(FieldProvenance.entity_type == ClaimEntityType.PROJECT)
            .where(FieldProvenance.entity_id == project_id)
            .where(Evidence.source_url == candidate.primary_source_url)
        ).scalars()
        return rows.first()


def validate_candidate_for_promotion(
    candidate: ProjectCandidate,
    *,
    allow_unresolved_name: bool,
    allow_incomplete: bool,
) -> list[str]:
    errors: list[str] = []
    if candidate.status == "promoted" and not candidate.promoted_project_id:
        errors.append("candidate_already_promoted_without_project_reference")
    if not candidate.primary_source_url:
        errors.append("candidate_missing_primary_source_url")
    if not has_public_source_references(candidate):
        errors.append("candidate_missing_public_source_references")
    if not candidate.candidate_name:
        errors.append("candidate_missing_name")
    elif candidate.candidate_name.startswith(UNRESOLVED_NAME_PREFIX) and not allow_unresolved_name:
        errors.append("candidate_name_unresolved")
    if not normalize_state(candidate.state) and not allow_incomplete:
        errors.append("candidate_missing_state")
    return errors


def has_public_source_references(candidate: ProjectCandidate) -> bool:
    if candidate.primary_source_url:
        return True
    return bool(candidate.discovered_source_ids_json or candidate.discovered_source_claim_ids_json)


def normalize_state(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(str(value).split()).strip()
    if not cleaned:
        return None
    if cleaned.lower() == "virginia":
        return "VA"
    if len(cleaned) == 2:
        return cleaned.upper()
    return None


def normalize_lifecycle(value: str | None) -> LifecycleState:
    if value:
        for state in LifecycleState:
            if value == state.value:
                return state
    return LifecycleState.CANDIDATE_UNVERIFIED


def build_project(candidate: ProjectCandidate) -> Project:
    return Project(
        canonical_name=candidate.candidate_name,
        developer=candidate.developer,
        state=normalize_state(candidate.state),
        county=candidate.county,
        lifecycle_state=normalize_lifecycle(candidate.lifecycle_state),
        candidate_metadata_json=project_metadata(candidate),
    )


def update_project_from_candidate(project: Project, candidate: ProjectCandidate) -> None:
    project.canonical_name = candidate.candidate_name
    project.developer = candidate.developer
    project.state = normalize_state(candidate.state)
    project.county = candidate.county
    project.lifecycle_state = normalize_lifecycle(candidate.lifecycle_state)
    project.candidate_metadata_json = project_metadata(candidate)


def project_metadata(candidate: ProjectCandidate) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "source": "project_candidate_promotion",
        "project_candidate_id": str(candidate.id),
        "primary_source_url": candidate.primary_source_url,
        "candidate_confidence": candidate.confidence,
        "discovered_source_ids": candidate.discovered_source_ids_json or [],
        "discovered_source_claim_ids": candidate.discovered_source_claim_ids_json or [],
    }
    if candidate.city:
        metadata["city"] = candidate.city
    if candidate.utility:
        metadata["utility"] = candidate.utility
    if candidate.load_mw is not None:
        metadata["load_mw"] = candidate.load_mw
    return metadata


def source_title(candidate: ProjectCandidate) -> str | None:
    raw = candidate.raw_metadata_json
    if isinstance(raw, dict):
        titles = raw.get("source_titles")
        if isinstance(titles, list):
            for title in titles:
                if title:
                    return str(title)[:255]
    return candidate.candidate_name


def build_evidence(candidate: ProjectCandidate) -> Evidence:
    return Evidence(
        source_type=SourceType.REGULATORY_RECORD,
        source_date=None,
        source_url=candidate.primary_source_url,
        source_rank=1,
        title=source_title(candidate),
        extracted_text=candidate.evidence_excerpt,
        reviewer_status=ReviewerStatus.REVIEWED,
        reviewed_at=datetime.now(timezone.utc),
        reviewed_by=PROMOTION_REVIEWER,
        review_notes="Created during explicit project candidate promotion.",
    )


def with_promotion_metadata(raw_metadata: dict | list | None, project_id: uuid.UUID, evidence_id: uuid.UUID) -> dict[str, Any]:
    metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {"raw_metadata": raw_metadata}
    metadata["promotion"] = {
        "promoted_project_id": str(project_id),
        "promotion_evidence_id": str(evidence_id),
        "promoted_by": PROMOTION_REVIEWER,
        "promoted_at": datetime.now(timezone.utc).isoformat(),
    }
    return metadata


def mapping_warnings(candidate: ProjectCandidate) -> list[str]:
    warnings: list[str] = []
    if candidate.city:
        warnings.append("candidate_city_stored_in_project_metadata")
    if candidate.utility:
        warnings.append("candidate_utility_stored_in_project_metadata")
    if candidate.load_mw is not None:
        warnings.append("candidate_load_mw_stored_in_project_metadata")
    return warnings
