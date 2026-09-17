"""Backfill review candidates from persisted baseline audits; never mutate audits."""
from __future__ import annotations

import math
import uuid
from dataclasses import asdict, dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.imported_dataset import ImportedCandidateLink, ImportedDatasetRow, ImportedDatasetRun
from app.models.project_candidate import ProjectCandidate
from app.services.baseline_dataset_profiles import PROFILES, public_url, fingerprint
from app.services.csv_candidate_dedupe import CsvCandidateDedupeService, DuplicateDecision, normalized_text
from app.services.csv_dataset_importer import NormalizedCsvRow, build_project_candidate, clean_text


@dataclass
class BackfillSummary:
    dataset: str
    dry_run: bool
    import_run_id: str | None = None
    offset: int = 0
    rows_checked: int = 0
    rows_eligible: int = 0
    rows_skipped_already_linked: int = 0
    rows_skipped_missing_identity: int = 0
    rows_skipped_missing_location: int = 0
    rows_skipped_missing_coordinates_when_only_mappable: int = 0
    rows_skipped_possible_duplicate: int = 0
    rows_skipped_existing_candidate_duplicate: int = 0
    rows_skipped_missing_public_source_url: int = 0
    rows_skipped_invalid_or_supporting: int = 0
    would_create_candidates: int = 0
    created_candidates: int = 0
    created_candidate_ids: list[str] = field(default_factory=list)
    created_candidate_links: int = 0
    created_projects: int = 0
    created_evidence: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    row_details: list[dict] | None = None

    def to_dict(self):
        result = asdict(self)
        if self.row_details is None:
            result.pop('row_details')
        return result


def coordinate(value, bound):
    try:
        number = float(value)
        return number if math.isfinite(number) and abs(number) <= bound else None
    except (ValueError, TypeError):
        return None


def backfill_candidates(db: Session, *, dataset: str, confirm: bool = False,
                        limit: int | None = None, offset: int = 0, import_run_id: str | None = None,
                        only_mappable: bool = False, include_possible_duplicates: bool = False,
                        include_row_details: bool = False):
    if include_row_details and confirm:
        raise ValueError('include_row_details requires dry-run mode')
    if dataset not in PROFILES:
        raise ValueError('unsupported baseline dataset')
    if limit is not None and limit < 0:
        raise ValueError('limit must be non-negative')
    if offset < 0:
        raise ValueError('offset must be non-negative')
    run_id = uuid.UUID(import_run_id) if import_run_id else None
    summary = BackfillSummary(dataset, not confirm, str(run_id) if run_id else None, offset=offset)
    result = summary
    if include_row_details:
        result.row_details = []
    query = select(ImportedDatasetRow).where(ImportedDatasetRow.dataset_name == dataset)
    if run_id:
        query = query.where(ImportedDatasetRow.run_id == run_id)
    # Canonical import order with a unique audit-ID tie breaker. Replay the
    # preceding rows as read-only context before selecting the reported window:
    # page boundaries must not change greedy duplicate decisions.
    query = query.order_by(ImportedDatasetRow.created_at, ImportedDatasetRow.run_id,
                           ImportedDatasetRow.source_file, ImportedDatasetRow.row_number, ImportedDatasetRow.id)
    if limit is not None:
        query = query.limit(offset + limit if limit else 0)
    audits = list(db.scalars(query))
    links = list(db.scalars(select(ImportedCandidateLink).order_by(ImportedCandidateLink.id)))
    linked = {link.imported_row_id for link in links}
    linked_candidates = {link.imported_row_id: str(link.linked_record_id) for link in links
                         if link.linked_record_type == 'project_candidate' and link.linked_record_id}
    candidate_ids = {key: str(id_) for key, id_ in db.execute(select(ProjectCandidate.candidate_key, ProjectCandidate.id))}
    keys = set(candidate_ids)
    dedupe = CsvCandidateDedupeService(db)
    planned = []
    prior = []
    prior_ids = []
    key_audit_ids = {}
    for index, audit in enumerate(audits):
        in_window = index >= offset
        # Context rows can affect decisions, but never counts, details or writes.
        summary = result if in_window else BackfillSummary(dataset, not confirm)
        summary.rows_checked += 1
        n = dict(audit.normalized_row_json) if isinstance(audit.normalized_row_json, dict) else {}
        n.update(latitude=coordinate(n.get('latitude'), 90), longitude=coordinate(n.get('longitude'), 180))
        urls = [u for u in (audit.source_urls_json or []) if isinstance(u, str) and public_url(u)
                and u.rstrip('/') != (audit.dataset_source or '').rstrip('/')]
        detail = {
            'audit_row_id': str(audit.id), 'source_name': PROFILES[dataset].display_name,
            'facility_name': n.get('name'), 'operator': n.get('operator'),
            'city': n.get('city'), 'state': n.get('state'),
            'latitude': n['latitude'], 'longitude': n['longitude'],
            'public_source_url': urls[0] if urls else None,
            'matched_candidate_id': None, 'matched_project_id': None, 'matched_audit_row_id': None,
        }

        def classify(classification, reason, decision=None):
            if not include_row_details or not in_window:
                return
            detail.update(classification=classification, reason=reason)
            significant = [m for m in decision.matches if m.status in
                           {'exact_duplicate', 'likely_same_project', 'possible_duplicate'}] if decision else []
            rank = {'exact_duplicate': 0, 'likely_same_project': 1, 'possible_duplicate': 2}
            for match in sorted(significant, key=lambda m: (rank[m.status], m.record_type, m.record_id or '')):
                field = {'project_candidate': 'matched_candidate_id', 'project': 'matched_project_id',
                         'imported_row': 'matched_audit_row_id'}.get(match.record_type)
                if field and detail[field] is None:
                    detail[field] = prior_ids[int(match.record_id) - 1] if match.record_type == 'imported_row' else match.record_id
            result.row_details.append(detail)

        if audit.id in linked or audit.linked_project_candidate_id:
            summary.rows_skipped_already_linked += 1
            detail['matched_candidate_id'] = str(audit.linked_project_candidate_id) if audit.linked_project_candidate_id else linked_candidates.get(audit.id)
            classify('already_linked', 'Audit row already has an import link or linked candidate.')
            # Preserve the full audit comparison context after a planned row is
            # linked. Candidate dedupe's projection omits coordinates, country,
            # external IDs and secondary URLs; it cannot replace this context.
            prior.append(n)
            prior_ids.append(str(audit.id))
            continue
        run = db.get(ImportedDatasetRun, audit.run_id)
        if not run or run.dry_run or run.dataset_name != dataset or audit.errors_json or n.get('dataset_row_type') != 'data_center':
            summary.rows_skipped_invalid_or_supporting += 1
            classify('invalid_or_supporting', 'Audit is invalid, supporting-only, or not from a confirmed matching import run.')
            continue
        lat, lon = coordinate(n.get('latitude'), 90), coordinate(n.get('longitude'), 180)
        n.update(latitude=lat, longitude=lon)
        coords = lat is not None and lon is not None
        name = clean_text(n.get('name'))
        if not name:
            summary.rows_skipped_missing_identity += 1
            classify('skipped_missing_identity', 'Name and dataset ID, state/country, or coordinate identity required.')
            continue
        location = any(clean_text(n.get(k)) for k in ('state', 'country', 'city', 'county', 'address')) or coords
        if not location:
            summary.rows_skipped_missing_location += 1
            classify('skipped_missing_location', 'No usable location field or coordinate pair.')
            continue
        if not (clean_text(n.get('external_dataset_id')) or clean_text(n.get('state')) or clean_text(n.get('country')) or coords):
            summary.rows_skipped_missing_identity += 1
            classify('skipped_missing_identity', 'Name and dataset ID, state/country, or coordinate identity required.')
            continue
        if only_mappable and not coords:
            summary.rows_skipped_missing_coordinates_when_only_mappable += 1
            classify('skipped_missing_coordinates_when_only_mappable', 'Mappable-only preview requires finite, in-range latitude and longitude.')
            continue
        key = 'baseline:' + (n.get('row_fingerprint') or fingerprint({'dataset': dataset, 'row': audit.raw_row_json}))
        decision = dedupe.evaluate_row({'normalized': n}, prior_rows=prior)
        # Inspect matches too: legacy dedupe considers country-only identity insufficient.
        exact = key in keys or audit.duplicate_status == 'exact_duplicate' or any(m.status == 'exact_duplicate' for m in decision.matches)
        if exact:
            summary.rows_skipped_existing_candidate_duplicate += 1
            detail['matched_candidate_id'] = candidate_ids.get(key)
            detail['matched_audit_row_id'] = key_audit_ids.get(key)
            classify('existing_candidate_duplicate', 'Exact duplicate: ' + ', '.join(
                sorted({reason for m in decision.matches if m.status == 'exact_duplicate' for reason in m.reasons})
                or ['existing candidate key or audit exact-duplicate flag']), decision)
            continue
        possible = audit.duplicate_status in {'possible_duplicate', 'likely_same_project'} or any(
            m.status in {'possible_duplicate', 'likely_same_project'} for m in decision.matches)
        # Retain name/country review protection for this batch where legacy logic lacks it.
        identity_match = next((i for i, p in enumerate(prior) if normalized_text(p.get('name')) == normalized_text(name) and
            any(n.get(k) and normalized_text(n[k]) == normalized_text(p.get(k)) for k in ('state', 'country'))), None)
        possible = possible or identity_match is not None
        if identity_match is not None:
            detail['matched_audit_row_id'] = prior_ids[identity_match]
        if possible and not include_possible_duplicates:
            summary.rows_skipped_possible_duplicate += 1
            classify('possible_duplicate', 'Possible duplicate: ' + ', '.join(
                sorted({reason for m in decision.matches if m.status in {'likely_same_project', 'possible_duplicate'} for reason in m.reasons})
                or (['same_normalized_name_and_state_or_country'] if identity_match is not None else ['audit duplicate flag'])), decision)
            continue
        warnings = list(audit.warnings_json or [])
        if not urls:
            warnings.append('missing_public_source_url: dataset provenance is not project evidence')
            summary.warnings.append(f'row {audit.id}: missing public source URL; review candidate only')
        if possible:
            warnings.append('possible_duplicate: explicitly included for analyst review')
        n.update(dataset_name=dataset, import_kind='baseline_dataset_import', import_run_id=str(audit.run_id),
                 citation=n.get('citation') or run.citation, license_note=n.get('license_note') or run.license_note)
        row = NormalizedCsvRow(dataset, audit.dataset_source, audit.source_file, audit.row_number,
            audit.raw_row_json if isinstance(audit.raw_row_json, dict) else {}, n, urls, warnings=warnings,
            duplicate_decision=DuplicateDecision('possible_duplicate' if possible else 'distinct',
                audit.duplicate_cluster_key, decision.reasons, decision.matches))
        classify('would_create_candidate', 'Eligible unverified review candidate' +
                 ('; possible duplicate explicitly included' if possible else '; no blocking duplicate signal') +
                 ('; public source URL missing' if not urls else ''), decision)
        if in_window:
            planned.append((audit, row, key))
        prior.append(n)
        prior_ids.append(str(audit.id))
        keys.add(key)
        key_audit_ids[key] = str(audit.id)
    summary = result
    summary.rows_eligible = summary.would_create_candidates = len(planned)
    if not confirm:
        return summary
    for audit, row, key in planned:
        candidate = build_project_candidate(row, key)
        candidate.claim_count = 0
        candidate.lifecycle_state = 'dataset_import_needs_review'
        candidate.raw_metadata_json = {**candidate.raw_metadata_json,
            'import_kind': 'baseline_dataset_import', 'import_run_id': str(audit.run_id),
            'imported_row_id': str(audit.id), 'dataset_display_name': PROFILES[dataset].display_name,
            'latitude': row.normalized['latitude'], 'longitude': row.normalized['longitude'],
            'normalized_row': row.to_persisted_normalized(),
            'imported_rows': [{'imported_row_id': str(audit.id), 'import_run_id': str(audit.run_id), 'dataset_name': dataset}]}
        db.add(candidate)
        db.flush()
        db.add(ImportedCandidateLink(imported_row_id=audit.id, linked_record_type='project_candidate',
            linked_record_id=candidate.id, duplicate_status=row.duplicate_decision.status,
            duplicate_cluster_key=audit.duplicate_cluster_key,
            match_reasons_json=['baseline_candidate_backfill_needs_review']))
        summary.created_candidates += 1
        summary.created_candidate_links += 1
        if len(summary.created_candidate_ids) < 100:
            summary.created_candidate_ids.append(str(candidate.id))
    db.flush()
    return summary
