from __future__ import annotations

import csv
import hashlib
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.imported_dataset import ImportedCandidateLink, ImportedDatasetRow, ImportedDatasetRun
from app.models.project_candidate import ProjectCandidate
from app.services.csv_candidate_dedupe import CsvCandidateDedupeService, DuplicateDecision, clean_text


URL_RE = re.compile(r"https?://[^\s,;)\]]+")
STATE_BY_NAME = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "florida": "FL",
    "georgia": "GA",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "new york": "NY",
    "north carolina": "NC",
    "north dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
}


@dataclass
class NormalizedCsvRow:
    dataset_name: str
    dataset_source: str | None
    source_file: str
    row_number: int
    raw_row: dict[str, Any]
    normalized: dict[str, Any]
    source_urls: list[str]
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    unmapped_columns: list[str] = field(default_factory=list)
    duplicate_decision: DuplicateDecision | None = None
    linked_project_candidate_id: str | None = None

    def to_persisted_normalized(self) -> dict[str, Any]:
        return {
            **self.normalized,
            "unmapped_columns": self.unmapped_columns,
            "duplicate": self.duplicate_decision.to_dict() if self.duplicate_decision else None,
        }


@dataclass
class CsvDatasetImportSummary:
    dataset: str
    input: str
    rows_read: int = 0
    rows_imported: int = 0
    rows_skipped: int = 0
    candidates_created: int = 0
    candidates_updated: int = 0
    candidate_links_created: int = 0
    exact_duplicates: int = 0
    likely_same_project: int = 0
    possible_duplicates: int = 0
    distinct: int = 0
    insufficient_information: int = 0
    skipped_candidate_missing_identity: int = 0
    skipped_candidate_missing_provenance: int = 0
    unmapped_columns: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    promoted: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BaselineImportSummary:
    dataset: str
    input: str
    import_run_id: str
    dry_run: bool
    rows_read: int = 0
    rows_valid: int = 0
    rows_invalid: int = 0
    would_create_import_records: int = 0
    would_create_candidates: int = 0
    created_import_records: int = 0
    created_candidates: int = 0
    duplicate_rows_skipped: int = 0
    possible_duplicates_flagged: int = 0
    rows_missing_identity: int = 0
    rows_missing_coordinates: int = 0
    rows_missing_public_source_url: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CsvDatasetImporter:
    def __init__(self, db: Session | None = None):
        self.db = db

    def import_file(
        self,
        *,
        dataset: str,
        input_path: str | Path,
        confirm: bool = False,
        limit: int | None = None,
        encoding: str = "utf-8",
        source_url: str | None = None,
        license_note: str | None = None,
        citation: str | None = None,
        create_candidates: bool = False,
        dedupe_only: bool = False,
        dataset_version: str | None = None,
        import_run_id: str | None = None,
    ) -> CsvDatasetImportSummary | BaselineImportSummary:
        from app.services.baseline_dataset_profiles import PROFILES
        if dataset in PROFILES:
            if dedupe_only and create_candidates:
                raise ValueError("dedupe_only cannot be combined with create_candidates")
            return self.import_baseline_file(
                dataset=dataset, input_path=input_path, confirm=confirm, limit=limit,
                encoding=encoding, source_url=source_url, license_note=license_note,
                citation=citation, create_candidates=create_candidates,
                dataset_version=dataset_version, import_run_id=import_run_id,
            )
        path = Path(input_path)
        summary = CsvDatasetImportSummary(dataset=dataset, input=str(path))
        rows = self.read_csv(path, encoding=encoding, limit=limit)
        summary.rows_read = len(rows)
        normalized_rows = self.normalize_rows(dataset, rows, source_file=str(path), dataset_source=source_url)
        for row in normalized_rows:
            if license_note:
                row.normalized["license_note"] = license_note
            if citation:
                row.normalized["citation"] = citation
        dedupe = CsvCandidateDedupeService(self.db)
        decisions = dedupe.evaluate_rows([{"normalized": row.normalized} for row in normalized_rows])
        for row, decision in zip(normalized_rows, decisions, strict=True):
            row.duplicate_decision = decision
            if decision.status == "exact_duplicate":
                summary.exact_duplicates += 1
            elif decision.status == "likely_same_project":
                summary.likely_same_project += 1
            elif decision.status == "possible_duplicate":
                summary.possible_duplicates += 1
            elif decision.status == "distinct":
                summary.distinct += 1
            elif decision.status == "insufficient_information":
                summary.insufficient_information += 1
            summary.warnings.extend(f"row {row.row_number}: {warning}" for warning in row.warnings)
            summary.errors.extend(f"row {row.row_number}: {error}" for error in row.errors)

        summary.unmapped_columns = sorted({column for row in normalized_rows for column in row.unmapped_columns})
        if not confirm:
            summary.rows_skipped = len(normalized_rows)
            if create_candidates:
                for row in normalized_rows:
                    eligibility = candidate_eligibility(row)
                    if not eligibility.can_create:
                        add_candidate_skip(row, eligibility, summary)
                        continue
                    linked_candidate = candidate_match_from_decision(row.duplicate_decision)
                    if linked_candidate:
                        summary.candidates_updated += 1
                        summary.candidate_links_created += 1
                    else:
                        summary.candidates_created += 1
                        summary.candidate_links_created += 1
                summary.warnings.append("dry_run_no_records_written")
            return summary

        if self.db is None:
            raise ValueError("db session is required when confirm=True")

        run = ImportedDatasetRun(
            dataset_name=dataset,
            dataset_version=dataset_version,
            dataset_source=source_url,
            source_file=str(path),
            retrieved_at=datetime.now(timezone.utc),
            license_note=license_note,
            citation=citation,
            dry_run=False,
            summary_json=None,
        )
        self.db.add(run)
        self.db.flush()

        existing_by_key: dict[str, ProjectCandidate] = {}
        if create_candidates and not dedupe_only:
            existing_by_key = self._existing_candidates_by_key(normalized_rows)

        for row in normalized_rows:
            candidate = None
            candidate_link_match = None
            if create_candidates and not dedupe_only and can_create_candidate(row):
                candidate_link_match = candidate_match_from_decision(row.duplicate_decision)
                if candidate_link_match is not None:
                    candidate = self.db.get(ProjectCandidate, candidate_link_match.record_id)
                candidate_key = candidate_key_for_row(row)
                if candidate is None:
                    candidate = existing_by_key.get(candidate_key)
                if candidate is None:
                    candidate = build_project_candidate(row, candidate_key)
                    self.db.add(candidate)
                    self.db.flush()
                    existing_by_key[candidate_key] = candidate
                    summary.candidates_created += 1
                else:
                    update_dataset_candidate(candidate, row)
                    summary.candidates_updated += 1
                row.linked_project_candidate_id = str(candidate.id)
            elif create_candidates:
                add_candidate_skip(row, candidate_eligibility(row), summary)

            imported_row = ImportedDatasetRow(
                run_id=run.id,
                dataset_name=dataset,
                dataset_version=dataset_version,
                dataset_source=source_url,
                source_file=str(path),
                row_number=row.row_number,
                raw_row_json=row.raw_row,
                normalized_row_json=row.to_persisted_normalized(),
                source_urls_json=row.source_urls,
                duplicate_status=row.duplicate_decision.status if row.duplicate_decision else "insufficient_information",
                duplicate_cluster_key=row.duplicate_decision.cluster_key if row.duplicate_decision else None,
                linked_project_candidate_id=candidate.id if candidate else None,
                warnings_json=row.warnings,
                errors_json=row.errors,
            )
            self.db.add(imported_row)
            self.db.flush()
            if candidate is not None:
                link_reasons = ["created_from_imported_row"] if candidate_link_match is None else candidate_link_match.reasons
                self.db.add(
                    ImportedCandidateLink(
                        imported_row_id=imported_row.id,
                        linked_record_type="project_candidate",
                        linked_record_id=candidate.id,
                        duplicate_status=row.duplicate_decision.status if row.duplicate_decision else "distinct",
                        duplicate_cluster_key=row.duplicate_decision.cluster_key if row.duplicate_decision else None,
                        match_reasons_json=link_reasons,
                    )
                )
                append_imported_row_metadata(candidate, row, imported_row)
                imported_row.linked_project_candidate_id = candidate.id
                summary.candidate_links_created += 1
            for match in row.duplicate_decision.matches if row.duplicate_decision else []:
                if candidate is not None and match.record_type == "project_candidate" and match.record_id == str(candidate.id):
                    continue
                self.db.add(
                    ImportedCandidateLink(
                        imported_row_id=imported_row.id,
                        linked_record_type=match.record_type,
                        linked_record_id=match.record_id if match.record_type in {"project_candidate", "project"} else None,
                        duplicate_status=match.status,
                        duplicate_cluster_key=match.cluster_key,
                        match_reasons_json=match.reasons,
                    )
                )
            summary.rows_imported += 1

        run.summary_json = summary.to_dict()
        self.db.flush()
        return summary

    def import_baseline_file(
        self, *, dataset: str, input_path: str | Path, confirm: bool = False,
        limit: int | None = None, encoding: str = "utf-8-sig", source_url: str | None = None,
        license_note: str | None = None, citation: str | None = None,
        create_candidates: bool = False, dataset_version: str | None = None,
        import_run_id: str | None = None,
    ) -> BaselineImportSummary:
        from app.services.baseline_dataset_profiles import (
            PROFILES, baseline_identity, filename_warning, normalize_baseline_row,
        )
        from app.services.csv_candidate_dedupe import close_coordinates, normalized_text

        if limit is not None and limit < 0:
            raise ValueError("limit must be non-negative")
        if confirm and self.db is None:
            raise ValueError("confirmed import requires a database session")
        run_id = uuid.UUID(import_run_id) if import_run_id else uuid.uuid4()
        profile = PROFILES[dataset]
        summary = BaselineImportSummary(dataset, str(input_path), str(run_id), not confirm)
        summary.warnings.extend(filename_warning(dataset, str(input_path)))
        if self.db is not None and self.db.get(ImportedDatasetRun, run_id) is not None:
            raise ValueError("import_run_id already exists; use a new UUID")
        # The same audit tables, candidate builder, and duplicate service are used.
        existing = list(self.db.scalars(select(ImportedDatasetRow))) if self.db is not None else []
        prior = [r.normalized_row_json for r in existing if isinstance(r.normalized_row_json, dict)]
        dedupe = CsvCandidateDedupeService(self.db)
        rows = self.read_csv(Path(input_path), encoding=encoding, limit=limit)
        summary.rows_read = len(rows)
        planned: list[tuple[NormalizedCsvRow, bool]] = []
        for raw in rows:
            malformed = None in raw or any(value is None for value in raw.values())
            safe_raw = {key if key is not None else "__extra_columns": value for key, value in raw.items()}
            row = normalize_baseline_row(dataset, safe_raw, source_file=str(input_path),
                import_run_id=str(run_id), source_url=source_url, citation=citation, license_note=license_note)
            if malformed:
                row.errors.append("malformed_csv_row_width")
            n = row.normalized
            missing_identity = not baseline_identity(n)
            summary.rows_missing_identity += int(missing_identity)
            summary.rows_missing_coordinates += int(n.get("latitude") is None or n.get("longitude") is None)
            summary.rows_missing_public_source_url += int(not row.source_urls)
            summary.rows_invalid += int(bool(row.errors))
            summary.rows_valid += int(not row.errors)
            # Only byte-equivalent row content within dataset/type is auto-skipped.
            # Same IDs with changed fields must retain a new audit row for review.
            exact = any(p.get("row_fingerprint") == n["row_fingerprint"] for p in prior)
            if exact:
                summary.duplicate_rows_skipped += 1
                summary.warnings.append(f"row {row.row_number}: exact_row_already_audited_or_in_input")
                summary.errors.extend(f"row {row.row_number}: {error}" for error in row.errors)
                continue
            decision = dedupe.evaluate_row({"normalized": n})
            reasons = list(decision.reasons) if decision.status in {"exact_duplicate", "likely_same_project", "possible_duplicate"} else []
            for previous in prior:
                same_id = (n.get("external_dataset_id") and n.get("dataset_name") == previous.get("dataset_name")
                           and n.get("dataset_row_type") == previous.get("dataset_row_type")
                           and n["external_dataset_id"] == previous.get("external_dataset_id"))
                same_name = bool(normalized_text(n.get("name")) and normalized_text(n.get("name")) == normalized_text(previous.get("name")))
                same_location = any(n.get(key) and normalized_text(n[key]) == normalized_text(previous.get(key)) for key in ("state", "country"))
                nearby = close_coordinates(n.get("latitude"), n.get("longitude"), previous.get("latitude"), previous.get("longitude"))
                if same_id:
                    reasons.append("same_dataset_row_id_changed_content")
                if same_name and (same_location or nearby):
                    reasons.append("same_name_location_or_nearby_coordinates")
                if set(row.source_urls) & set(previous.get("source_urls") or []):
                    reasons.append("shared_source_url_requires_review")
            possible = bool(reasons)
            if possible:
                summary.possible_duplicates_flagged += 1
                row.warnings.append("possible_duplicate: no automatic candidate merge or creation")
            row.duplicate_decision = DuplicateDecision(
                "possible_duplicate" if possible else "insufficient_information" if missing_identity else "distinct",
                decision.cluster_key, sorted(set(reasons)), decision.matches,
            )
            can_create = bool(create_candidates and not row.errors and not possible and candidate_eligibility(row).can_create)
            summary.would_create_import_records += 1
            summary.would_create_candidates += int(can_create)
            summary.errors.extend(f"row {row.row_number}: {error}" for error in row.errors)
            summary.warnings.extend(f"row {row.row_number}: {warning}" for warning in row.warnings)
            planned.append((row, can_create))
            prior.append(n)
        if not confirm:
            summary.warnings.append("dry_run_no_records_or_reports_written")
            return summary

        assert self.db is not None
        run = ImportedDatasetRun(id=run_id, dataset_name=dataset, dataset_version=dataset_version,
            dataset_source=source_url or profile.source_url, source_file=str(input_path),
            retrieved_at=datetime.now(timezone.utc), license_note=license_note or profile.license_note,
            citation=citation or profile.citation, dry_run=False)
        self.db.add(run)
        self.db.flush()
        for row, can_create in planned:
            audit = ImportedDatasetRow(run_id=run_id, dataset_name=dataset, dataset_version=dataset_version,
                dataset_source=row.dataset_source, source_file=str(input_path), row_number=row.row_number,
                raw_row_json=row.raw_row, normalized_row_json=row.to_persisted_normalized(),
                source_urls_json=row.source_urls, duplicate_status=row.duplicate_decision.status,
                duplicate_cluster_key=row.duplicate_decision.cluster_key,
                warnings_json=row.warnings, errors_json=row.errors)
            self.db.add(audit)
            self.db.flush()
            summary.created_import_records += 1
            if can_create:
                candidate = build_project_candidate(row, "baseline:" + row.normalized["row_fingerprint"])
                candidate.lifecycle_state = "dataset_import_needs_review"
                candidate.claim_count = 0
                candidate.raw_metadata_json = {
                    **candidate.raw_metadata_json,
                    "import_kind": "baseline_dataset_import", "import_run_id": str(run_id),
                    "dataset_display_name": profile.display_name,
                    "normalized_row": row.to_persisted_normalized(),
                    "imported_rows": [{"imported_row_id": str(audit.id), "import_run_id": str(run_id), "dataset_name": dataset}],
                }
                # Keep provenance=dataset_import for existing verifier/admission guards.
                # Never update or reuse an existing candidate, including promoted ones.
                self.db.add(candidate)
                self.db.flush()
                audit.linked_project_candidate_id = candidate.id
                self.db.add(ImportedCandidateLink(imported_row_id=audit.id, linked_record_type="project_candidate",
                    linked_record_id=candidate.id, duplicate_status="distinct",
                    match_reasons_json=["baseline_dataset_import_needs_review"]))
                summary.created_candidates += 1
        run.summary_json = summary.to_dict()
        self.db.flush()
        return summary

    def read_csv(self, input_path: Path, *, encoding: str, limit: int | None) -> list[dict[str, Any]]:
        with input_path.open("r", encoding=encoding, newline="") as handle:
            reader = csv.DictReader(handle)
            rows: list[dict[str, Any]] = []
            for index, row in enumerate(reader, start=2):
                if limit is not None and len(rows) >= limit:
                    break
                rows.append({"__row_number": index, **dict(row)})
            return rows

    def normalize_rows(
        self,
        dataset: str,
        rows: list[dict[str, Any]],
        *,
        source_file: str,
        dataset_source: str | None,
    ) -> list[NormalizedCsvRow]:
        if dataset == "epoch_frontier":
            return [normalize_epoch_row(row, source_file=source_file, dataset_source=dataset_source) for row in rows]
        if dataset == "fractracker_open_us":
            return [normalize_fractracker_row(row, source_file=source_file, dataset_source=dataset_source) for row in rows]
        return [normalize_flexible_row(dataset, row, source_file=source_file, dataset_source=dataset_source) for row in rows]

    def _existing_candidates_by_key(self, rows: list[NormalizedCsvRow]) -> dict[str, ProjectCandidate]:
        if self.db is None:
            return {}
        keys = [candidate_key_for_row(row) for row in rows if can_create_candidate(row)]
        if not keys:
            return {}
        records = self.db.scalars(select(ProjectCandidate).where(ProjectCandidate.candidate_key.in_(keys)))
        return {record.candidate_key: record for record in records}


def normalize_epoch_row(
    raw: dict[str, Any],
    *,
    source_file: str,
    dataset_source: str | None,
) -> NormalizedCsvRow:
    file_name = Path(source_file).name
    if file_name == "data_center_timelines.csv":
        return normalize_epoch_timeline_row(raw, source_file=source_file, dataset_source=dataset_source)
    if file_name in {"data_center_cooling_towers.csv", "data_center_chillers.csv"}:
        return normalize_epoch_equipment_row(raw, source_file=source_file, dataset_source=dataset_source)

    mapped = {
        "name": value_for(raw, "Name"),
        "developer": value_for(raw, "Owner"),
        "tenant_user": value_for(raw, "Users"),
        "load_mw": parse_number(value_for(raw, "Current power (MW)")),
        "country": value_for(raw, "Country"),
        "address": value_for(raw, "Address"),
        "evidence_text": join_text(value_for(raw, "Selected Sources"), value_for(raw, "Notes")),
        "project_family": value_for(raw, "Project"),
        "utility": value_for(raw, "Energy companies"),
        "supporting_source_url": first_url(value_for(raw, "Calculations sheet")),
        "dataset_row_type": "data_center",
    }
    source_urls = urls_from_values(raw.values())
    if mapped["supporting_source_url"] and mapped["supporting_source_url"] not in source_urls:
        source_urls.append(mapped["supporting_source_url"])
    mapped["source_urls"] = source_urls
    mapped["dataset_name"] = "epoch_frontier"
    mapped["dataset_source"] = dataset_source
    warnings = identity_warnings(mapped)
    return normalized_csv_row("epoch_frontier", raw, mapped, source_file, dataset_source, warnings, mapped_columns={
        "Name",
        "Owner",
        "Users",
        "Current power (MW)",
        "Country",
        "Address",
        "Selected Sources",
        "Notes",
        "Project",
        "Energy companies",
        "Calculations sheet",
    })


def normalize_epoch_timeline_row(
    raw: dict[str, Any],
    *,
    source_file: str,
    dataset_source: str | None,
) -> NormalizedCsvRow:
    mapped = {
        "name": value_for(raw, "Data center"),
        "event_date": value_for(raw, "Date"),
        "event_text": value_for(raw, "Construction status"),
        "it_power_mw": parse_number(value_for(raw, "IT power (MW)")),
        "load_mw": parse_number(value_for(raw, "Power (MW)")),
        "water_use_mgd": parse_number(value_for(raw, "Water use (MGD)")),
        "capital_cost": first_present(raw, "Capital cost", "Capital cost ($)", "Capital cost (USD)", "Cost"),
        "claims": compact_dict(
            {
                "it_power_mw": parse_number(value_for(raw, "IT power (MW)")),
                "power_mw": parse_number(value_for(raw, "Power (MW)")),
                "water_use_mgd": parse_number(value_for(raw, "Water use (MGD)")),
                "capital_cost": first_present(raw, "Capital cost", "Capital cost ($)", "Capital cost (USD)", "Cost"),
            }
        ),
        "dataset_row_type": "timeline",
    }
    source_urls = urls_from_values(raw.values())
    mapped["source_urls"] = source_urls
    mapped["dataset_name"] = "epoch_frontier"
    mapped["dataset_source"] = dataset_source
    warnings = identity_warnings(mapped)
    if mapped["name"]:
        mapped["linked_candidate_key_hint"] = candidate_key_from_parts("epoch_frontier", mapped["name"], None)
    return normalized_csv_row("epoch_frontier", raw, mapped, source_file, dataset_source, warnings, mapped_columns={
        "Data center",
        "Date",
        "Construction status",
        "IT power (MW)",
        "Power (MW)",
        "Water use (MGD)",
        "Capital cost",
        "Capital cost ($)",
        "Capital cost (USD)",
        "Cost",
    })


def normalize_epoch_equipment_row(
    raw: dict[str, Any],
    *,
    source_file: str,
    dataset_source: str | None,
) -> NormalizedCsvRow:
    mapped = {
        "name": first_present(raw, "Data center", "Name"),
        "dataset_row_type": "equipment_reference",
        "equipment_profile": {key: value for key, value in raw.items() if key != "__row_number" and clean_text(value)},
        "source_urls": urls_from_values(raw.values()),
        "dataset_name": "epoch_frontier",
        "dataset_source": dataset_source,
    }
    warnings = ["equipment_reference_not_candidate_input"]
    return normalized_csv_row("epoch_frontier", raw, mapped, source_file, dataset_source, warnings, mapped_columns=set(raw) - {"__row_number"})


def normalize_fractracker_row(
    raw: dict[str, Any],
    *,
    source_file: str,
    dataset_source: str | None,
) -> NormalizedCsvRow:
    mapped = flexible_mapping(raw)
    mapped["dataset_name"] = "fractracker_open_us"
    mapped["dataset_source"] = dataset_source
    mapped["dataset_row_type"] = "data_center"
    warnings = identity_warnings(mapped)
    mapped_columns = set(mapped.pop("_mapped_columns", []))
    return normalized_csv_row("fractracker_open_us", raw, mapped, source_file, dataset_source, warnings, mapped_columns=mapped_columns)


def normalize_flexible_row(
    dataset: str,
    raw: dict[str, Any],
    *,
    source_file: str,
    dataset_source: str | None,
) -> NormalizedCsvRow:
    mapped = flexible_mapping(raw)
    mapped["dataset_name"] = dataset
    mapped["dataset_source"] = dataset_source
    mapped["dataset_row_type"] = "data_center"
    warnings = identity_warnings(mapped)
    mapped_columns = set(mapped.pop("_mapped_columns", []))
    return normalized_csv_row(dataset, raw, mapped, source_file, dataset_source, warnings, mapped_columns=mapped_columns)


def flexible_mapping(raw: dict[str, Any]) -> dict[str, Any]:
    lookup = {canonical_column(key): key for key in raw if key != "__row_number"}
    mapped_columns: set[str] = set()

    def take(*names: str) -> str | None:
        fallback: str | None = None
        for name in names:
            key = lookup.get(canonical_column(name))
            if key is not None:
                mapped_columns.add(key)
                value = value_for(raw, key)
                if value:
                    return value
                fallback = value
        return fallback

    def take_all_matching(*needles: str) -> list[str]:
        values: list[str] = []
        canonical_needles = [canonical_column(needle) for needle in needles]
        for canonical_key, original_key in lookup.items():
            if any(needle in canonical_key for needle in canonical_needles):
                mapped_columns.add(original_key)
                value = value_for(raw, original_key)
                if value:
                    values.append(value)
        return values

    mapped = {
        "name": take("name", "project name", "facility name", "data center", "datacenter"),
        "lifecycle_state": take("status", "construction status", "project status"),
        "developer": take("company", "operator", "operator name", "operator_name", "owner", "developer", "company/operator"),
        "address": take("address", "street address", "location"),
        "city": take("city", "municipality"),
        "county": take("county"),
        "state": normalize_state(take("state")),
        "latitude": parse_number(take("latitude", "lat")),
        "longitude": parse_number(take("longitude", "long", "lon", "lng")),
        "load_mw": parse_number(take("mw", "power mw", "load mw", "power", "capacity mw")),
        "square_feet": parse_number(take("square footage", "facility size sqft", "facility_size_sqft", "sqft", "sq ft")),
        "cooling": take("cooling", "cooling type", "cooling source", "cooling_source"),
        "power_source": take("power source", "energy source", "dedicated power plant"),
        "external_dataset_id": take("id", "objectid", "dataset id", "facility id"),
    }
    source_texts = [
        *take_all_matching("source"),
        *take_all_matching("url", "website"),
    ]
    note_text = take("notes", "note", "purpose")
    if note_text:
        source_texts.append(note_text)
    mapped["evidence_text"] = join_text(*source_texts)
    source_urls = urls_from_values(raw.values())
    mapped["source_urls"] = source_urls
    mapped["_mapped_columns"] = list(mapped_columns)
    return compact_dict(mapped)


def normalized_csv_row(
    dataset: str,
    raw: dict[str, Any],
    mapped: dict[str, Any],
    source_file: str,
    dataset_source: str | None,
    warnings: list[str],
    *,
    mapped_columns: set[str],
) -> NormalizedCsvRow:
    row_number = int(raw.get("__row_number") or 0)
    raw_without_internal = {key: value for key, value in raw.items() if key != "__row_number"}
    source_urls = list(dict.fromkeys([url for url in mapped.get("source_urls") or [] if url]))
    if dataset_source and dataset_source not in source_urls:
        source_urls.append(dataset_source)
    mapped = compact_dict({**mapped, "source_urls": source_urls})
    unmapped_columns = sorted(
        key for key, value in raw_without_internal.items() if key not in mapped_columns and clean_text(value)
    )
    return NormalizedCsvRow(
        dataset_name=dataset,
        dataset_source=dataset_source,
        source_file=source_file,
        row_number=row_number,
        raw_row=raw_without_internal,
        normalized=mapped,
        source_urls=source_urls,
        warnings=warnings,
        errors=[],
        unmapped_columns=unmapped_columns,
    )


def can_create_candidate(row: NormalizedCsvRow) -> bool:
    return candidate_eligibility(row).can_create


@dataclass(frozen=True)
class CandidateEligibility:
    can_create: bool
    missing_identity: bool = False
    missing_provenance: bool = False
    reasons: tuple[str, ...] = ()


def candidate_eligibility(row: NormalizedCsvRow) -> CandidateEligibility:
    normalized = row.normalized
    reasons: list[str] = []
    if normalized.get("dataset_row_type") != "data_center":
        return CandidateEligibility(False, missing_identity=True, reasons=("not_project_candidate_row",))
    has_name = bool(clean_text(normalized.get("name")))
    has_location = bool(
        normalized.get("state")
        or normalized.get("country")
        or normalized.get("address")
        or normalized.get("county")
        or normalized.get("city")
        or (normalized.get("latitude") is not None and normalized.get("longitude") is not None)
    )
    has_provenance = bool(
        row.source_urls
        or clean_text(normalized.get("dataset_source"))
        or clean_text(normalized.get("citation"))
        or clean_text(normalized.get("license_note"))
        or clean_text(normalized.get("evidence_text"))
        or clean_text(normalized.get("supporting_source_url"))
    )
    if not has_name:
        reasons.append("missing_candidate_name")
    if not has_location:
        reasons.append("missing_location_signal")
    if not has_provenance:
        reasons.append("missing_public_source_or_dataset_provenance")
    return CandidateEligibility(
        can_create=has_name and has_location and has_provenance,
        missing_identity=not (has_name and has_location),
        missing_provenance=not has_provenance,
        reasons=tuple(reasons),
    )


def add_candidate_skip(row: NormalizedCsvRow, eligibility: CandidateEligibility, summary: CsvDatasetImportSummary) -> None:
    if eligibility.missing_identity:
        summary.skipped_candidate_missing_identity += 1
    if eligibility.missing_provenance:
        summary.skipped_candidate_missing_provenance += 1
    reason = "candidate_not_created:" + ",".join(eligibility.reasons or ("unknown",))
    row.warnings.append(reason)
    summary.warnings.append(f"row {row.row_number}: {reason}")


def candidate_match_from_decision(decision: DuplicateDecision | None):
    if decision is None or decision.status not in {"exact_duplicate", "likely_same_project"}:
        return None
    for match in decision.matches:
        if match.record_type == "project_candidate" and match.record_id and match.status in {"exact_duplicate", "likely_same_project"}:
            return match
    return None


def build_project_candidate(row: NormalizedCsvRow, candidate_key: str) -> ProjectCandidate:
    normalized = row.normalized
    metadata = candidate_metadata(row)
    return ProjectCandidate(
        candidate_key=candidate_key,
        candidate_name=clean_text(normalized.get("name"))[:255],
        developer=clean_text(normalized.get("developer")),
        state=clean_text(normalized.get("state")),
        county=clean_text(normalized.get("county")),
        city=clean_text(normalized.get("city")),
        utility=clean_text(normalized.get("utility")),
        load_mw=normalized.get("load_mw"),
        lifecycle_state=clean_text(normalized.get("lifecycle_state")) or "dataset_import_needs_review",
        confidence=0.45,
        status="needs_review",
        source_count=len(row.source_urls),
        claim_count=len(normalized.get("claims") or {}),
        primary_source_url=row.source_urls[0] if row.source_urls else None,
        discovered_source_ids_json=[],
        discovered_source_claim_ids_json=[],
        evidence_excerpt=clean_text(normalized.get("evidence_text")) or clean_text(normalized.get("event_text")),
        raw_metadata_json=metadata,
        auto_admit_eligible=False,
        verification_status=None,
    )


def update_dataset_candidate(candidate: ProjectCandidate, row: NormalizedCsvRow) -> None:
    normalized = row.normalized
    metadata = candidate_metadata(row)
    if not candidate.developer and normalized.get("developer"):
        candidate.developer = clean_text(normalized.get("developer"))
    if not candidate.state and normalized.get("state"):
        candidate.state = clean_text(normalized.get("state"))
    if not candidate.county and normalized.get("county"):
        candidate.county = clean_text(normalized.get("county"))
    if not candidate.utility and normalized.get("utility"):
        candidate.utility = clean_text(normalized.get("utility"))
    if candidate.load_mw is None and normalized.get("load_mw") is not None:
        candidate.load_mw = normalized.get("load_mw")
    if not candidate.primary_source_url and row.source_urls:
        candidate.primary_source_url = row.source_urls[0]
    if not candidate.evidence_excerpt:
        candidate.evidence_excerpt = clean_text(normalized.get("evidence_text")) or clean_text(normalized.get("event_text"))
    candidate.source_count = max(candidate.source_count or 0, len(row.source_urls))
    candidate.status = "needs_review"
    candidate.auto_admit_eligible = False
    existing_metadata = candidate.raw_metadata_json if isinstance(candidate.raw_metadata_json, dict) else {}
    candidate.raw_metadata_json = merge_candidate_metadata(existing_metadata, metadata, row)


def append_imported_row_metadata(candidate: ProjectCandidate, row: NormalizedCsvRow, imported_row: ImportedDatasetRow) -> None:
    existing_metadata = candidate.raw_metadata_json if isinstance(candidate.raw_metadata_json, dict) else {}
    metadata = candidate_metadata(row)
    metadata["imported_row_id"] = str(imported_row.id)
    candidate.raw_metadata_json = merge_candidate_metadata(existing_metadata, metadata, row)


def candidate_metadata(row: NormalizedCsvRow) -> dict[str, Any]:
    return {
        "provenance": "dataset_import",
        "dataset_name": row.dataset_name,
        "dataset_source": row.dataset_source,
        "source_file": row.source_file,
        "row_number": row.row_number,
        "source_urls": row.source_urls,
        "citation": row.normalized.get("citation"),
        "license_note": row.normalized.get("license_note"),
        "duplicate_status": row.duplicate_decision.status if row.duplicate_decision else None,
        "duplicate_cluster_key": row.duplicate_decision.cluster_key if row.duplicate_decision else None,
        "address": row.normalized.get("address"),
        "country": row.normalized.get("country"),
        "tenant_user": row.normalized.get("tenant_user"),
        "project_family": row.normalized.get("project_family"),
        "raw_row": row.raw_row,
        "warnings": row.warnings,
    }


def merge_candidate_metadata(existing: dict[str, Any], metadata: dict[str, Any], row: NormalizedCsvRow) -> dict[str, Any]:
    imported_rows = list(existing.get("imported_rows") or [])
    row_ref = {
        "imported_row_id": metadata.get("imported_row_id"),
        "dataset_name": row.dataset_name,
        "source_file": row.source_file,
        "row_number": row.row_number,
        "duplicate_status": metadata.get("duplicate_status"),
        "duplicate_cluster_key": metadata.get("duplicate_cluster_key"),
    }
    if row_ref not in imported_rows:
        imported_rows.append(row_ref)
    source_urls = list(dict.fromkeys([*(existing.get("source_urls") or []), *row.source_urls]))
    return {
        **existing,
        "provenance": "dataset_import",
        "dataset_name": existing.get("dataset_name") or row.dataset_name,
        "dataset_source": existing.get("dataset_source") or row.dataset_source,
        "source_file": existing.get("source_file") or row.source_file,
        "row_number": existing.get("row_number") or row.row_number,
        "source_urls": source_urls,
        "citation": existing.get("citation") or row.normalized.get("citation"),
        "license_note": existing.get("license_note") or row.normalized.get("license_note"),
        "duplicate_status": row.duplicate_decision.status if row.duplicate_decision else existing.get("duplicate_status"),
        "duplicate_cluster_key": row.duplicate_decision.cluster_key if row.duplicate_decision else existing.get("duplicate_cluster_key"),
        "latest_dataset_import": metadata,
        "imported_rows": imported_rows,
    }


def candidate_key_for_row(row: NormalizedCsvRow) -> str:
    normalized = row.normalized
    return candidate_key_from_parts(row.dataset_name, normalized.get("name"), normalized.get("state") or normalized.get("address"))


def candidate_key_from_parts(dataset: str, name: Any, location: Any) -> str:
    text = "|".join(str(part or "").strip().lower() for part in (dataset, name, location))
    return hashlib.sha256(f"dataset_import:{text}".encode("utf-8")).hexdigest()


def value_for(raw: dict[str, Any], key: str) -> str | None:
    return clean_text(raw.get(key))


def first_present(raw: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = value_for(raw, key)
        if value:
            return value
    return None


def parse_number(value: Any) -> float | None:
    text = clean_text(value)
    if text is None:
        return None
    text = text.replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def normalize_state(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    if len(text) == 2:
        return text.upper()
    return STATE_BY_NAME.get(text.lower(), text)


def urls_from_values(values: Any) -> list[str]:
    urls: list[str] = []
    for value in values:
        text = clean_text(value)
        if text:
            urls.extend(URL_RE.findall(text))
    return list(dict.fromkeys(url.rstrip(".") for url in urls))


def first_url(value: Any) -> str | None:
    urls = urls_from_values([value])
    return urls[0] if urls else None


def join_text(*values: Any) -> str | None:
    parts = [clean_text(value) for value in values if clean_text(value)]
    return "\n".join(parts) if parts else None


def compact_dict(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value not in (None, "", [], {})}


def canonical_column(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def identity_warnings(mapped: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if not clean_text(mapped.get("name")):
        warnings.append("missing_name")
    if not (mapped.get("state") or mapped.get("address") or (mapped.get("latitude") is not None and mapped.get("longitude") is not None)):
        warnings.append("missing_location")
    if not mapped.get("source_urls"):
        warnings.append("missing_public_source_url")
    return warnings
