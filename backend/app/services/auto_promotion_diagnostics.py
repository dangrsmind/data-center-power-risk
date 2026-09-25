"""Read-only presentation of existing promotion decisions; never evaluates gates."""
from collections import Counter

DIAGNOSTICS_VERSION = 'auto-promotion-diagnostics-v0.1'
DECISION_TYPES = ('would_promote', 'skip_already_promoted', 'skip_missing_coordinates',
                  'skip_low_confidence', 'skip_weak_source', 'skip_duplicate_risk', 'exception_review')
PRIMARY_BLOCKERS = {
    'would_promote': ('none', 'none', 'All conservative automatic promotion gates passed; coordinates remain unverified.'),
    'skip_already_promoted': ('already_promoted', 'already_promoted', 'Candidate is already linked/promoted; no repair or update will be attempted.'),
    'skip_missing_coordinates': ('coordinates', 'missing_coordinates', 'No valid stored coordinate pair is available through the preservation path.'),
    'skip_low_confidence': ('confidence', 'low_confidence', 'Candidate confidence is below threshold or invalid.'),
    'skip_weak_source': ('primary_source', 'weak_source', 'A specific recognized operator/government primary source is required.'),
    'skip_duplicate_risk': ('no_duplicate', 'duplicate_risk', 'Existing Project, another selected candidate, or an audit duplicate flag requires review.'),
}
GATE_LABELS = {
    'dataset_policy': ('dataset_policy', 'Dataset policy is unknown or disables automated Projects.'),
    'audit_provenance': ('audit_provenance', 'Imported candidates require linked audit-row provenance.'),
    'candidate_status': ('candidate_status', 'Candidate is not in a promotable review state.'),
    'review_decision': ('review_hold', 'An existing analyst decision requires review; automation will not override it.'),
    'verification_conflicts': ('verification_hold', 'Stored verification status or errors require review.'),
    'identity_location': ('identity_location', 'A resolved candidate name and recognized US state are required.'),
    'project_type': ('project_type', 'The source or row does not establish a specific build or expansion.'),
    'alignment': ('source_alignment', 'Primary-source alignment must be fully aligned.'),
    'lifecycle': ('lifecycle', 'An explicit active data-center build lifecycle is required.'),
    'row_consistency': ('row_consistency', 'Source-row identity, lifecycle, type or geography requires review.'),
    'coordinate_consistency': ('coordinate_conflict', 'Stored coordinate pairs disagree; manual resolution is required.'),
    'stored_warnings': ('stored_warnings', 'Stored warnings require review.'),
}


def diagnostic_row(candidate, rows, project, normalized, evaluation):
    """Capture the pre-write candidate snapshot, using the evaluated coordinate path.

    Primary categories are mutually exclusive. Secondary failures stay in the
    reasons/gates rather than being counted as additional primary blockers.
    """
    decision = evaluation['promotion_decision']
    decision = 'would_promote' if decision == 'promote' else decision
    if decision in PRIMARY_BLOCKERS:
        blocker, category, primary_reason = PRIMARY_BLOCKERS[decision]
    else:
        blocker = next((key for key, passed in evaluation['gates'].items() if not passed), 'exception_review')
        if blocker.startswith('audit_') and blocker != 'audit_provenance':
            category, primary_reason = 'audit_row', 'An imported audit row has errors, context-only data, or insufficient provenance.'
        else:
            category, primary_reason = GATE_LABELS.get(blocker, ('exception_review', 'Candidate requires exception review.'))
    reasons = list(dict.fromkeys([primary_reason, *evaluation['promotion_reasons']]))
    # Already-promoted is an idempotent skip, not a request to fix old gate failures.
    blocking = [] if decision in {'would_promote', 'skip_already_promoted'} else list(evaluation['promotion_reasons'])
    raw = candidate.raw_metadata_json if isinstance(candidate.raw_metadata_json, dict) else {}
    provenance = {
        'kind': raw.get('provenance') or raw.get('import_kind'),
        'dataset_ids': list(evaluation['dataset_ids']),
        'dataset_source': raw.get('dataset_source'),
        'source_file': raw.get('source_file'),
        'row_number': raw.get('row_number'),
        'import_run_id': raw.get('import_run_id'),
        'source_urls': raw.get('source_urls') or normalized.get('source_urls') or [],
        'discovered_source_ids': candidate.discovered_source_ids_json or [],
        'discovered_source_claim_ids': candidate.discovered_source_claim_ids_json or [],
        'imported_rows': [
            {'imported_row_id': str(row.id), 'run_id': str(row.run_id), 'dataset_name': row.dataset_name,
             'dataset_source': row.dataset_source, 'source_file': row.source_file, 'row_number': row.row_number}
            for row in rows
        ],
    }
    return {
        **evaluation,
        'candidate_status': candidate.status or 'unknown',
        'latitude': project.latitude,
        'longitude': project.longitude,
        'coordinate_availability': 'available' if evaluation['gates']['coordinates'] else 'missing_or_invalid',
        'promoted_project_id': str(candidate.promoted_project_id) if candidate.promoted_project_id else None,
        'promotion_decision': decision,
        'primary_blocker': blocker,
        'blocker_category': category,
        'decision_reasons': reasons,
        'blocking_reasons': blocking,
        'source_quality_status': evaluation['source_quality']['source_quality'],
        'source_alignment_status': evaluation['source_row_alignment']['source_row_alignment'],
        'verification_status': candidate.verification_status,
        'lifecycle_state': candidate.lifecycle_state,
        'source_lifecycle_state': normalized.get('lifecycle_state'),
        'primary_source_url': candidate.primary_source_url,
        'provenance': provenance,
        # Compatibility with simple readers using generic decision/status/reasons.
        'decision': decision,
        'status': candidate.status or 'unknown',
        'reasons': reasons,
    }


def grouped_diagnostics(rows):
    counts = Counter(row['promotion_decision'] for row in rows)
    blockers = Counter(row['blocker_category'] for row in rows)
    return {
        'diagnostics_version': DIAGNOSTICS_VERSION,
        'decisions_by_type': {key: counts[key] for key in DECISION_TYPES},
        'blockers_by_category': dict(sorted(blockers.items())),
        'candidates_by_status': dict(sorted(Counter(row['candidate_status'] for row in rows).items())),
        'candidates_by_lifecycle_state': dict(sorted(Counter(row['lifecycle_state'] or 'unknown' for row in rows).items())),
        'candidates_by_coordinate_availability': {
            key: sum(row['coordinate_availability'] == key for row in rows)
            for key in ('available', 'missing_or_invalid')
        },
        'top_blocker_examples': {
            category: [row for row in rows if row['blocker_category'] == category][:5]
            for category in sorted(blockers) if category != 'none'
        },
    }
