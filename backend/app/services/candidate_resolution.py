"""Read-only backlog classification. Recommendations never execute resolutions."""
from collections import Counter
import re

from sqlalchemy import select

from app.models.discovered_source import DiscoveredSourceRecord, DiscoveredSourceClaim
from app.models.imported_dataset import ImportedDatasetRow
from app.models.project_candidate import ProjectCandidate
from app.services.automated_candidate_promotion import (
    auto_promote_candidates, candidate_record, mapping, state_code,
)
from app.services.baseline_entity_taxonomy import classify_entity_taxonomy
from app.services.baseline_source_row_alignment import identity
from app.services.csv_dataset_importer import STATE_BY_NAME

VERSION = 'candidate-resolution-v0.1'
CLASSES = ('promotable_now', 'resolvable_missing_coordinates', 'resolvable_missing_identity',
           'unresolved_placeholder', 'context_only_or_supporting', 'low_confidence',
           'already_promoted', 'exception_review')
ACTIONS = {
    'promotable_now': 'auto_promote_candidate',
    'resolvable_missing_coordinates': 'resolve_coordinates',
    'resolvable_missing_identity': 'resolve_identity_from_source',
    'unresolved_placeholder': 'suppress_from_promotion',
    'context_only_or_supporting': 'keep_as_context',
    'low_confidence': 'suppress_from_promotion',
    'already_promoted': 'already_promoted_no_action',
    'exception_review': 'manual_exception_review',
}
PLACEHOLDER_WARNINGS = {'unresolved_candidate_name', 'missing_state', 'missing_project_specific_claim'}
CONTEXT_ENTITIES = {'power_generation_asset', 'grid_interconnection_asset', 'cooling_water_asset',
                    'equipment_supply_chain_signal', 'policy_permitting_case'}
CONTEXT_PURPOSES = {'facility_baseline', 'infrastructure_context', 'supply_chain_signal',
                    'permitting_or_policy_signal'}
PROJECT_CLAIMS = {'possible_project_name', 'developer', 'city', 'county', 'state', 'load_mw', 'utility'}


def string_list(value):
    if isinstance(value, str):
        return [value] if value else []
    return [v for v in value if isinstance(v, str) and v] if isinstance(value, list) else []


def classify(candidate, linked, sources, claims, diagnostic):
    raw = mapping(candidate.raw_metadata_json)
    normalized = candidate_record(candidate, linked)
    taxonomy = classify_entity_taxonomy(normalized, diagnostic['source_quality'], normalized['source_urls'], mapping(raw.get('raw_row')))
    stored = [*string_list(raw.get('warnings')), *string_list(candidate.triage_warnings_json),
              *string_list(candidate.verification_errors_json), *string_list(normalized.get('warnings'))]
    for row in linked:
        stored += string_list(row.warnings_json) + string_list(row.errors_json)
    for source in sources:
        stored += string_list(mapping(source.raw_metadata_json).get('warnings'))
    warnings = set(stored)
    gates = diagnostic['gates']
    failed = {key for key, passed in gates.items() if not passed}
    name = (candidate.candidate_name or '').strip()
    synthetic = bool(re.match(r'^(unresolved|placeholder)\b', name, re.I))
    if synthetic:
        warnings.add('unresolved_candidate_name')
    if state_code(candidate.state) not in set(STATE_BY_NAME.values()):
        warnings.add('missing_state')
    source_refs = string_list(candidate.discovered_source_ids_json)
    claim_refs = string_list(candidate.discovered_source_claim_ids_json)
    useful_claims = [c for c in claims if c.status != 'rejected' and c.claim_type in PROJECT_CLAIMS
                     and c.source_url == candidate.primary_source_url]
    if (source_refs or claim_refs) and not useful_claims:
        warnings.add('missing_project_specific_claim')
    if not gates['coordinates']:
        warnings.add('missing_coordinates')
    if not gates['primary_source']:
        warnings.add('non_official_source_only')
    if diagnostic['source_alignment_status'] != 'aligned':
        warnings.add(diagnostic['source_alignment_status'] if diagnostic['source_alignment_status'] != 'unknown' else 'insufficient_source_row_alignment')
    if diagnostic['lifecycle_stage'] in {'unknown', 'speculative_or_unverified'}:
        warnings.add('unknown_lifecycle')
    if not gates['confidence']:
        warnings.add('low_candidate_confidence' if (candidate.confidence or 0) < .5 else 'moderate_candidate_confidence')

    # Explicit row type and taxonomy are stronger context signals than source weakness alone.
    row_types = {str(mapping(r.normalized_row_json).get('dataset_row_type') or '') for r in linked}
    row_types.add(str(normalized.get('dataset_row_type') or ''))
    context_rows = bool(row_types & {'timeline', 'equipment', 'equipment_reference', 'supporting_context', 'infrastructure_context'})
    context_sources = bool(sources) and all(s.source_type in {'grid_context', 'context', 'supporting_context'} for s in sources)
    context = (context_rows or context_sources or 'context_only_source' in warnings
               or normalized.get('entity_type') == 'supporting_context'
               or taxonomy['entity_type'] in CONTEXT_ENTITIES
               or taxonomy['candidate_purpose'] in CONTEXT_PURPOSES
               or diagnostic['lifecycle_stage'] == 'existing_operational')
    placeholder_warnings = sorted(warnings & PLACEHOLDER_WARNINGS)
    conflict = (diagnostic['source_alignment_status'] in {'geography_mismatch', 'facility_or_operator_mismatch', 'cancelled_or_rejected_project'}
                or not gates['coordinate_consistency'] or candidate.review_decision not in {None, '', 'ready_for_verification'}
                or candidate.verification_status not in {None, '', 'auto_admit_eligible'}
                or diagnostic['lifecycle_stage'] in {'cancelled', 'retired'})
    unresolved_identity = not name or not identity(name) or name.casefold() in {'unknown', 'unnamed', 'tbd'}
    # Identity work is only suggested with useful project-specific provenance and
    # otherwise viable gates. It is not a promise of promotion after a name edit.
    identity_repair_gates = {'identity_location', 'alignment', 'row_consistency', 'coordinates'}
    identity_resolvable = (unresolved_identity and gates['primary_source'] and gates['project_type']
                           and gates['lifecycle'] and failed <= identity_repair_gates)

    if candidate.promoted_project_id or candidate.status == 'promoted':
        resolution, blocker, reason = 'already_promoted', 'already_promoted', 'Candidate is already linked/promoted; no action or repair is proposed.'
    elif synthetic:
        resolution, blocker, reason = 'unresolved_placeholder', 'synthetic_identity', 'Synthetic unresolved candidate name is not a real project identity; coordinates cannot resolve this.'
    elif conflict:
        resolution, blocker, reason = 'exception_review', 'conflicting_or_held_record', 'Conflicting source/location/lifecycle or an existing review hold requires exception review.'
    elif context:
        resolution, blocker, reason = 'context_only_or_supporting', 'context_not_project', 'Stored row/source type or taxonomy describes supporting context, equipment, policy, timeline or an operating facility.'
    elif placeholder_warnings:
        resolution, blocker, reason = 'unresolved_placeholder', placeholder_warnings[0], 'Identity/project-specific support is unresolved: ' + ', '.join(placeholder_warnings) + '. Do not treat this as a coordinate-only gap.'
    elif not gates['no_duplicate']:
        resolution, blocker, reason = 'exception_review', 'duplicate_risk', 'A Project, selected candidate or stored duplicate flag may represent the same entity; do not merge or promote automatically.'
    elif diagnostic['promotion_eligible']:
        resolution, blocker, reason = 'promotable_now', 'none', 'The existing promotion dry-run gates all pass; this report performs no promotion.'
    elif failed == {'coordinates'} and not unresolved_identity:
        resolution, blocker, reason = 'resolvable_missing_coordinates', 'missing_coordinates', 'A real named project passes every promotion gate except coordinates; resolve coordinates and rerun all gates.'
    elif identity_resolvable:
        resolution, blocker, reason = 'resolvable_missing_identity', 'missing_identity', 'A specific strong source and active project lifecycle support identity research; the stored name is absent or generic.'
    elif not gates['confidence']:
        resolution, blocker, reason = 'low_confidence', 'low_confidence', 'Confidence is below the promotion threshold and the record is not clearly resolvable; exclude from promotion pending stronger support.'
    else:
        resolution, blocker, reason = 'exception_review', 'multiple_or_ambiguous_blockers', 'The record has blockers beyond a clear identity or coordinate repair; review the failed promotion gates.'
    return {
        **diagnostic, 'status': candidate.status, 'city': candidate.city, 'state': candidate.state,
        'county': candidate.county, 'normalized_state': state_code(candidate.state) or 'unknown',
        'warnings': sorted(warnings), 'stored_warnings': sorted(set(stored)), 'taxonomy': taxonomy,
        'resolution_class': resolution, 'primary_resolution_blocker': blocker,
        'resolution_reasons': list(dict.fromkeys([reason, *diagnostic['blocking_reasons']])),
        'recommended_next_action': ACTIONS[resolution],
        'failed_promotion_gates': sorted(failed),
        'linked_sources': [{'id': str(s.id), 'source_url': s.source_url, 'source_type': s.source_type,
                            'source_title': s.source_title, 'status': s.status} for s in sources],
        'project_specific_claim_count': len(useful_claims),
    }


def resolve_candidate_backlog(db, *, limit=None, min_confidence=.80, include_row_details=False):
    """Always read-only; there is intentionally no confirm/write parameter."""
    with db.no_autoflush:
        promotion = auto_promote_candidates(db, confirm=False, limit=limit,
            min_confidence=min_confidence, include_row_details=True)
        candidates = {str(c.id): c for c in db.scalars(select(ProjectCandidate))}
        audits = {str(r.id): r for r in db.scalars(select(ImportedDatasetRow))}
        sources = {str(s.id): s for s in db.scalars(select(DiscoveredSourceRecord))}
        claims = {str(c.id): c for c in db.scalars(select(DiscoveredSourceClaim))}
        rows = []
        for diagnostic in promotion['row_details']:
            candidate = candidates[diagnostic['candidate_id']]
            linked = [audits[id_] for id_ in diagnostic['imported_row_ids'] if id_ in audits]
            source_rows = [sources[id_] for id_ in string_list(candidate.discovered_source_ids_json) if id_ in sources]
            claim_rows = [claims[id_] for id_ in string_list(candidate.discovered_source_claim_ids_json) if id_ in claims]
            rows.append(classify(candidate, linked, source_rows, claim_rows, diagnostic))
        classes = Counter(row['resolution_class'] for row in rows)
        actions = Counter(row['recommended_next_action'] for row in rows)
        result = {
            'dry_run': True, 'report_version': VERSION, 'candidates_checked': len(rows),
            'candidates_matching_filters': promotion['candidates_matching_filters'], 'limit': limit,
            'min_confidence': min_confidence,
            'counts_by_resolution_class': {key: classes[key] for key in CLASSES},
            'counts_by_recommended_next_action': {key: actions[key] for key in sorted(set(ACTIONS.values()))},
            'counts_by_status': dict(sorted(Counter(row['status'] or 'unknown' for row in rows).items())),
            'counts_by_lifecycle_state': dict(sorted(Counter(row['lifecycle_state'] or 'unknown' for row in rows).items())),
            'counts_by_warning': dict(sorted(Counter(w for row in rows for w in row['warnings']).items())),
            'counts_by_state': dict(sorted(Counter(row['normalized_state'] for row in rows).items())),
            'top_examples_by_class': {key: [r for r in rows if r['resolution_class'] == key][:5] for key in CLASSES},
            'could_become_promotable_after_coordinate_resolution': classes['resolvable_missing_coordinates'],
            'should_be_suppressed_or_excluded_from_promotion': sum(classes[key] for key in
                ('unresolved_placeholder', 'context_only_or_supporting', 'low_confidence', 'exception_review')),
            'duplicate_risk_count': sum(not row['gates']['no_duplicate'] for row in rows),
            'promotion_decisions_by_type': promotion['decisions_by_type'],
        }
        if include_row_details:
            result['row_details'] = rows
        return result
