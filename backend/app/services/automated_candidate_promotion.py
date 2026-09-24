"""Offline, capped promotion. Writes only Projects and their source candidates."""
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import math
import uuid

from sqlalchemy import select, text

from app.core.enums import LifecycleState
from app.models.imported_dataset import ImportedCandidateLink, ImportedDatasetRow, ImportedDatasetRun
from app.models.project import Project
from app.models.project_candidate import ProjectCandidate
from app.services.baseline_dataset_profiles import public_url
from app.services.baseline_entity_taxonomy import classify_entity_taxonomy, lifecycle, words
from app.services.baseline_source_quality import classify_source_and_candidate
from app.services.baseline_source_row_alignment import classify_source_row_alignment, contains, primary_source_text
from app.services.candidate_coordinates import candidate_coordinates
from app.services.csv_candidate_dedupe import match_normalized_records, normalized_text
from app.services.csv_dataset_importer import STATE_BY_NAME
from app.services.open_dataset_registry import REGISTRY
from app.services.project_candidate_promotion import ProjectCandidatePromotionService, build_project

VERSION = 'automated-promotion-v0.1'
DECISIONS = ('promote', 'skip_already_promoted', 'skip_missing_coordinates', 'skip_low_confidence',
             'skip_weak_source', 'skip_duplicate_risk', 'exception_review')
DATASET_PROMOTION_ALLOWED = {'epoch_ai_data_centers'}
STRONG_SOURCES = {'government_or_regulatory', 'official_project_or_operator'}
ACTIVE_STAGES = {'proposed', 'under_construction', 'planned_expansion'}
DUPLICATES = {'exact_duplicate', 'likely_same_project', 'possible_duplicate'}


def mapping(value):
    return value if isinstance(value, dict) else {}


def state_code(value):
    return STATE_BY_NAME.get(str(value or '').strip().lower(), str(value or '').strip().upper())


def dataset_ids(candidate, rows):
    raw = mapping(candidate.raw_metadata_json)
    n = mapping(raw.get('normalized_row'))
    values = [raw.get('dataset_name'), raw.get('dataset_id'), n.get('dataset_name'),
              mapping(raw.get('automated_ingestion')).get('dataset_id'), *(r.dataset_name for r in rows)]
    values += [mapping(r).get('dataset_name') for r in (raw.get('imported_rows') if isinstance(raw.get('imported_rows'), list) else [])]
    return sorted({str(v) for v in values if v})


def candidate_record(candidate, rows):
    raw = mapping(candidate.raw_metadata_json)
    n = mapping(raw.get('normalized_row'))
    if not n and rows:
        n = mapping(rows[0].normalized_row_json)
    return {**n, 'name': candidate.candidate_name, 'state': state_code(candidate.state),
            'city': candidate.city, 'county': candidate.county, 'developer': candidate.developer,
            'load_mw': candidate.load_mw, 'source_urls': [candidate.primary_source_url] if candidate.primary_source_url and public_url(candidate.primary_source_url) else [],
            'lifecycle_state': n.get('lifecycle_state') or candidate.lifecycle_state}


def project_record(project):
    raw = mapping(project.candidate_metadata_json)
    return {**mapping(raw.get('normalized_row')), 'name': project.canonical_name,
            'state': state_code(project.state), 'county': project.county,
            'developer': project.developer or project.operator, 'latitude': project.latitude,
            'longitude': project.longitude, 'source_urls': [raw['primary_source_url']] if raw.get('primary_source_url') else []}


def conflict(left, right, record_id, record_type):
    left = {**left, 'source_urls': [u for u in left.get('source_urls', []) if isinstance(u, str) and public_url(u)]}
    right = {**right, 'source_urls': [u for u in right.get('source_urls', []) if isinstance(u, str) and public_url(u)]}
    match = match_normalized_records(left, right, record_id=record_id, record_type=record_type)
    if match.status in DUPLICATES:
        return match.to_dict()
    # Missing/inconsistent location is not permission to duplicate the same name.
    if normalized_text(left.get('name')) and normalized_text(left.get('name')) == normalized_text(right.get('name')):
        return {'record_id': record_id, 'record_type': record_type, 'status': 'possible_duplicate', 'reasons': ['same_name_requires_review']}
    return None


def evaluate(candidate, rows, runs, project, n, matches, min_confidence, known_cities):
    raw = mapping(candidate.raw_metadata_json)
    datasets = dataset_ids(candidate, rows)
    reasons = []
    gates = {}
    def gate(key, passed, reason):
        gates[key] = bool(passed)
        if not passed:
            reasons.append(reason)

    imported = bool(rows or datasets or raw.get('provenance') == 'dataset_import' or raw.get('import_kind'))
    policy_allowed = all(d in DATASET_PROMOTION_ALLOWED and d in REGISTRY and REGISTRY[d].auto_project_allowed for d in datasets)
    if imported and not datasets:
        policy_allowed = False
    gate('dataset_policy', policy_allowed, 'Dataset policy is unknown or disables automated Projects.')
    gate('audit_provenance', not imported or bool(rows), 'Imported candidates require linked audit-row provenance.')
    gate('candidate_status', candidate.status in {'needs_review', 'candidate'}, 'Candidate is not in a promotable review state.')
    gate('review_decision', candidate.review_decision in {None, '', 'ready_for_verification'}, 'An existing analyst decision requires review; automation will not override it.')
    gate('verification_conflicts', not candidate.verification_errors_json and candidate.verification_status in {None, '', 'auto_admit_eligible'}, 'Stored verification status/error requires review; quarantine and review holds cannot be bypassed.')
    gate('identity_location', bool(str(candidate.candidate_name or '').strip() and not candidate.candidate_name.strip().casefold().startswith('unresolved '))
         and n['state'] in set(STATE_BY_NAME.values()), 'Named candidate and recognized US state required.')
    gate('coordinates', project.latitude is not None and project.longitude is not None, 'No valid stored coordinate pair is available through the preservation path.')
    confidence = candidate.confidence
    gate('confidence', isinstance(confidence, (int, float)) and not isinstance(confidence, bool)
         and math.isfinite(confidence) and min_confidence <= confidence <= 1, 'Candidate confidence is below threshold or invalid.')
    quality = classify_source_and_candidate(candidate.primary_source_url, n)
    quality['quality_gate_reason'] = quality['quality_gate_reason'].replace('; analyst source review still required.', '; offline hint, not verification.')
    gate('primary_source', quality['source_quality'] in STRONG_SOURCES, 'A specific recognized operator/government primary source is required; news, social, broad and unknown sources are blocked.')
    gate('project_type', quality['candidate_type_allows_candidate_creation'], 'Primary source/row does not establish a specific build or expansion.')
    urls = n['source_urls']
    alignment = classify_source_row_alignment(n, urls, mapping(raw.get('raw_row')), known_cities=known_cities)
    gate('alignment', alignment['source_row_alignment'] == 'aligned', 'Primary-source alignment must be fully aligned: ' + alignment['source_row_alignment'])
    taxonomy = classify_entity_taxonomy(n, quality, urls)
    stage = lifecycle(words(n.get('lifecycle_state')))
    gate('lifecycle', lifecycle(words(candidate.lifecycle_state)) not in {'cancelled', 'retired', 'existing_operational'} and stage in ACTIVE_STAGES and taxonomy['entity_type'] in {'data_center_project', 'data_center_campus'}
         and taxonomy['candidate_purpose'] == 'build_review', 'Explicit active data-center build lifecycle required; context, operating, cancelled and unknown rows remain in review.')
    # Re-evaluate every available audit row, not just stored boolean gate results.
    records = [(n, mapping(raw.get('raw_row')))]
    if mapping(raw.get('normalized_row')):
        records.append((mapping(raw['normalized_row']), mapping(raw.get('raw_row'))))
    for row in rows:
        row_n = mapping(row.normalized_row_json)
        records.append((row_n, mapping(row.raw_row_json)))
        run = runs.get(row.run_id)
        gate('audit_' + str(row.id), bool(run and not run.dry_run and run.dataset_name == row.dataset_name)
             and not row.errors_json and row_n.get('dataset_row_type', 'data_center') == 'data_center'
             and candidate.primary_source_url in (row.source_urls_json or []),
             f'Imported row {row.id} has errors, is context-only, or lacks a confirmed matching run.')
    bad_records = False
    coordinate_pairs = set()
    pair = candidate_coordinates(raw)
    if pair[0] is not None:
        coordinate_pairs.add(pair)
    for record, source_raw in records:
        if not record:
            bad_records = True
            continue
        if record.get('name') and normalized_text(record['name']) != normalized_text(candidate.candidate_name):
            bad_records = True
        if record.get('state') and state_code(record['state']) != n['state']:
            bad_records = True
        pair = candidate_coordinates(record)
        if pair[0] is not None:
            coordinate_pairs.add(pair)
        if record.get('dataset_row_type', 'data_center') != 'data_center':
            bad_records = True
        if lifecycle(words(record.get('lifecycle_state'))) not in ACTIVE_STAGES:
            bad_records = True
        row_alignment = classify_source_row_alignment({**record, 'state': n['state']}, urls, source_raw, known_cities=known_cities)
        if row_alignment['source_row_alignment'] != 'aligned':
            bad_records = True
        source_text, _ = primary_source_text(candidate.primary_source_url, record, source_raw, urls)
        states = {code for name, code in STATE_BY_NAME.items() if contains(source_text, name)}
        if contains(source_text, 'west virginia'):
            states.discard('VA')
        if states - {n['state']}:
            bad_records = True
    gate('row_consistency', not bad_records, 'Source-row identity, lifecycle, type or geography conflicts/missing alignment require review.')
    gate('coordinate_consistency', len(coordinate_pairs) <= 1, 'Stored coordinate pairs disagree; manual resolution required.')
    stored_duplicate = raw.get('duplicate_status') in DUPLICATES or any(r.duplicate_status in DUPLICATES for r in rows) or any(
        mapping(record.get('duplicate')).get('status') in DUPLICATES for record, _ in records)
    warnings = [*(raw.get('warnings') or []), *(candidate.triage_warnings_json or [])]
    for row in rows:
        warnings.extend(row.warnings_json or [])
    warnings = [str(w) for w in warnings if w not in {'baseline_dataset_import_requires_analyst_review', 'dataset_import_requires_analyst_review'}] if all(isinstance(w, str) for w in warnings) else ['Malformed stored warnings']
    gate('stored_warnings', not warnings, 'Stored warning(s) require review: ' + '; '.join(warnings))
    gate('no_duplicate', not matches and not stored_duplicate, 'Existing Project, another selected candidate, or audit duplicate flag requires review.')
    if candidate.promoted_project_id or candidate.status == 'promoted':
        decision = 'skip_already_promoted'
        reasons = ['Candidate is already linked/promoted; no repair or update will be attempted.']
    elif not gates['coordinates']:
        decision = 'skip_missing_coordinates'
    elif not gates['confidence']:
        decision = 'skip_low_confidence'
    elif not gates['primary_source']:
        decision = 'skip_weak_source'
    elif not gates['no_duplicate']:
        decision = 'skip_duplicate_risk'
    elif not all(gates.values()):
        decision = 'exception_review'
    else:
        decision = 'promote'
        reasons = ['All conservative automatic promotion gates passed; coordinates remain unverified.']
    return {'candidate_id': str(candidate.id), 'candidate_name': candidate.candidate_name,
            'promotion_eligible': decision == 'promote', 'promotion_decision': decision,
            'promotion_reasons': reasons, 'blocking_warnings': [] if decision == 'promote' else reasons,
            'gates': gates, 'dataset_ids': datasets, 'source_url': candidate.primary_source_url,
            'confidence': confidence, 'min_confidence': min_confidence, 'source_quality': quality,
            'source_row_alignment': alignment, 'lifecycle_stage': stage, 'duplicate_matches': matches,
            'imported_row_ids': [str(r.id) for r in rows], 'engine_version': VERSION,
            'dataset_policies': {d: REGISTRY[d].snapshot() if d in REGISTRY else None for d in datasets},
            'source_policy': sorted(STRONG_SOURCES), 'automated_promotion_dataset_allowlist': sorted(DATASET_PROMOTION_ALLOWED)}


def auto_promote_candidates(db, *, confirm=False, max_promote=None, min_confidence=.80,
                            dataset=None, source=None, limit=None, candidate_ids=None, include_row_details=False):
    """Plan under a transaction lock, validate the cap, then atomically write.

    The caller supplies a clean session; confirmed mode owns commit/rollback.
    No Evidence/verification/admission service is invoked.
    """
    if not isinstance(min_confidence, (int, float)) or isinstance(min_confidence, bool) or not math.isfinite(min_confidence) or not 0 <= min_confidence <= 1:
        raise ValueError('min_confidence must be finite and between 0 and 1')
    if max_promote is not None and (type(max_promote) is not int or max_promote < 0):
        raise ValueError('max_promote must be a nonnegative integer')
    if confirm and max_promote is None:
        raise ValueError('--confirm requires --max-promote; nothing written')
    if limit is not None and (type(limit) is not int or limit < 0):
        raise ValueError('limit must be a nonnegative integer')
    if db.new or db.dirty or db.deleted:
        raise ValueError('Use a clean session; pending changes are not part of this operation')
    if confirm and db.in_transaction():
        raise ValueError('Confirmed promotion requires a fresh transaction')
    requested = {uuid.UUID(str(value)) for value in (candidate_ids or [])}
    try:
        with db.no_autoflush:
            if confirm:
                dialect = db.get_bind().dialect.name
                if dialect == 'sqlite':
                    db.execute(text('BEGIN IMMEDIATE'))
                elif dialect == 'postgresql':
                    # Also serializes against the automated open-dataset writer.
                    db.execute(text('SELECT pg_advisory_xact_lock(746281930)'))
                    db.execute(text('LOCK TABLE projects, project_candidates, imported_dataset_rows, imported_candidate_links, imported_dataset_runs IN SHARE ROW EXCLUSIVE MODE'))
                else:
                    raise ValueError('Confirmed mode supports SQLite/PostgreSQL only')
                db.expire_all()
            candidates = list(db.scalars(select(ProjectCandidate).order_by(ProjectCandidate.created_at, ProjectCandidate.id)))
            available = {c.id for c in candidates}
            if requested - available:
                raise ValueError('Unknown candidate ID(s): ' + ', '.join(sorted(str(v) for v in requested - available)))
            rows_by_candidate = defaultdict(dict)
            rows = {r.id: r for r in db.scalars(select(ImportedDatasetRow))}
            runs = {r.id: r for r in db.scalars(select(ImportedDatasetRun))}
            for row in rows.values():
                if row.linked_project_candidate_id:
                    rows_by_candidate[row.linked_project_candidate_id][row.id] = row
            duplicate_links = set()
            for link in db.scalars(select(ImportedCandidateLink).where(ImportedCandidateLink.linked_record_type == 'project_candidate')):
                if link.duplicate_status in DUPLICATES:
                    duplicate_links.add(link.linked_record_id)
                if link.imported_row_id in rows:
                    rows_by_candidate[link.linked_record_id][link.imported_row_id] = rows[link.imported_row_id]
            selected = []
            for candidate in candidates:
                linked = sorted(rows_by_candidate[candidate.id].values(), key=lambda r: (r.created_at, str(r.id)))
                if requested and candidate.id not in requested:
                    continue
                if dataset and dataset not in dataset_ids(candidate, linked):
                    continue
                if source and source.casefold() not in (candidate.primary_source_url or '').casefold():
                    continue
                selected.append((candidate, linked))
            matched_count = len(selected)
            if limit is not None:
                selected = selected[:limit]
            preservation = ProjectCandidatePromotionService(db)
            plans = []
            for candidate, linked in selected:
                project = build_project(candidate)
                preservation.preserve_coordinates(project, candidate)
                n = candidate_record(candidate, linked)
                n.update(latitude=project.latitude, longitude=project.longitude)
                plans.append((candidate, linked, project, n))
            projects = list(db.scalars(select(Project).order_by(Project.id)))  # Intentionally no 1,000-row cutoff.
            project_records = [(p, project_record(p)) for p in projects]
            cities = {c.city for c in candidates if c.city}
            decisions = []
            for candidate, linked, project, n in plans:
                matches = []
                if candidate.id in duplicate_links:
                    matches.append({'record_type': 'imported_candidate_link', 'status': 'possible_duplicate', 'reasons': ['stored_link_duplicate_flag']})
                for existing, record in project_records:
                    match = conflict(n, record, str(existing.id), 'project')
                    if mapping(existing.candidate_metadata_json).get('project_candidate_id') == str(candidate.id):
                        match = {'record_id': str(existing.id), 'record_type': 'project', 'status': 'exact_duplicate', 'reasons': ['existing_candidate_reference']}
                    if match:
                        matches.append(match)
                for other, _, _, record in plans:
                    if other.id != candidate.id:
                        match = conflict(n, record, str(other.id), 'selected_candidate')
                        if match:
                            matches.append(match)
                decisions.append(evaluate(candidate, linked, runs, project, n, matches, min_confidence, cities))
            counts = Counter(d['promotion_decision'] for d in decisions)
            report = {'dry_run': not confirm, 'engine_version': VERSION, 'candidates_checked': len(plans),
                      'candidates_matching_filters': matched_count, 'limit': limit, 'min_confidence': min_confidence,
                      'filters': {'dataset': dataset, 'source': source, 'candidate_ids': sorted(str(v) for v in requested)},
                      **{'would_' + key: counts[key] for key in DECISIONS}, 'promoted': 0,
                      'evidence_created': 0, 'top_examples': {key: [d for d in decisions if d['promotion_decision'] == key][:5] for key in DECISIONS}}
            if include_row_details:
                report['row_details'] = decisions
            if confirm and counts['promote'] > max_promote:
                raise ValueError(f"Eligible count {counts['promote']} exceeds --max-promote {max_promote}; nothing written")
            if confirm:
                batch_id = str(uuid.uuid4())
                now = datetime.now(timezone.utc).isoformat()
                for (candidate, linked, project, n), decision in zip(plans, decisions):
                    if not decision['promotion_eligible']:
                        continue
                    audit = {**deepcopy(decision), 'batch_id': batch_id, 'promoted_at': now,
                             'max_promote': max_promote, 'batch_counts': dict(counts)}
                    project.state = n['state']
                    project.lifecycle_state = LifecycleState.CANDIDATE_UNVERIFIED
                    project.candidate_metadata_json = {**project.candidate_metadata_json,
                        'candidate_provenance': deepcopy(candidate.raw_metadata_json),
                        'automated_promotion': audit, 'normalized_row': n}
                    db.add(project)
                    db.flush()
                    candidate.status = 'promoted'
                    candidate.promoted_project_id = project.id
                    candidate.raw_metadata_json = {**mapping(candidate.raw_metadata_json),
                        'automated_promotion': {**audit, 'promoted_project_id': str(project.id)}}
                db.commit()
                report['promoted'] = counts['promote']
            return report
    except Exception:
        if confirm:
            db.rollback()
        raise
