"""Versioned local-source policies. No fetching or inferred verification rights."""
from dataclasses import asdict, dataclass
from app.services.baseline_dataset_profiles import PROFILES

DECISIONS = ('auto_create_project', 'create_project_candidate', 'create_context_record_only',
             'skip_duplicate', 'exception_review', 'reject_or_ignore')

@dataclass(frozen=True)
class DatasetPolicy:
    dataset_id: str
    source_name: str
    canonical_source_url: str | None
    license_summary: str
    license_url: str | None
    attribution_text: str
    source_type: str = 'open_dataset_export'
    entity_scope: tuple = ('data_center', 'timeline', 'equipment_reference', 'infrastructure_context')
    geographic_scope: str = 'global'
    update_cadence: str = 'unknown; explicit local snapshots only'
    ingest_adapter: str = 'normalize_baseline_row'
    allowed_automated_outcomes: tuple = DECISIONS
    auto_project_allowed: bool = False
    auto_project_threshold: float = 0.85
    candidate_threshold: float = 0.60
    context_allowed: bool = True
    promotion_policy: str = 'direct unverified Project creation only through strict gates; no promotion/admission/verification'
    required_fields: tuple = ('name', 'location', 'public provenance')
    coordinate_policy: str = 'finite in-range pair required for Projects; missing/invalid pairs block automatic Projects'
    source_trust_score: float = 0.70
    policy_version: str = 'open-datasets-v0.1'

    def snapshot(self):
        return asdict(self)

REGISTRY = {
    key: DatasetPolicy(dataset_id=key, source_name=p.display_name,
        canonical_source_url=p.source_url, license_summary=p.license_note,
        license_url='https://creativecommons.org/licenses/by/4.0/' if key == 'epoch_ai_data_centers' else None,
        attribution_text=p.citation, geographic_scope='US' if key.startswith('fractracker') else 'global',
        auto_project_allowed=key == 'epoch_ai_data_centers',
        source_trust_score=0.9 if key == 'epoch_ai_data_centers' else 0.7)
    for key, p in PROFILES.items()
}
