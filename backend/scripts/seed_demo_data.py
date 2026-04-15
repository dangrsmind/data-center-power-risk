from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from math import log
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.enums import (
    CausalStrength,
    EventFamily,
    EventScope,
    LifecycleState,
    LoadKind,
    ReviewerStatus,
    ScoreRunType,
    SourceSignalType,
    SourceType,
    StressDirection,
    StressEntityType,
)
from app.core.db import SessionLocal, create_db_and_tables, engine
from app.models import Base
from app.models.evidence import Claim, Evidence, FieldProvenance
from app.models.event import Event
from app.models.project import Phase, PhaseLoad, Project
from app.models.quarterly import (
    PhaseQuarterScore,
    ProjectPhaseQuarter,
    QuarterlyLabel,
    QuarterlySnapshot,
    ScoreRun,
    StressObservation,
    StressScore,
)
from app.models.reference import Region, Utility
from app.services.mock_scoring_service import MockScoringInputs, MockScoringService


def d(value: str | int | float) -> Decimal:
    return Decimal(str(value))


@dataclass
class SeedProject:
    canonical_name: str
    developer: str
    operator: str
    state: str
    county: str
    lifecycle_state: LifecycleState
    announcement_date: date
    latest_update_date: date
    region_code: str
    utility_name: str
    phases: list[dict]
    project_stress_score: Decimal
    regional_stress_score: Decimal
    anomaly_score: Decimal
    snapshot_features: dict
    labels: dict
    event_family: EventFamily | None = None
    event_scope: EventScope | None = None
    event_date: date | None = None
    reason_class: str | None = None
    weak_label_weight: Decimal | None = None
    event_notes: str | None = None


REGIONS = [
    {"name": "ERCOT", "region_type": "RTO", "code": "ERCOT", "state": "TX"},
    {"name": "PJM", "region_type": "RTO", "code": "PJM", "state": None},
    {"name": "MISO South", "region_type": "RTO", "code": "MISO-S", "state": None},
    {"name": "APS Territory", "region_type": "utility_region", "code": "APS", "state": "AZ"},
    {"name": "NV Energy Territory", "region_type": "utility_region", "code": "NVE", "state": "NV"},
]


PROJECTS = [
    SeedProject(
        canonical_name="Red Mesa Compute Campus",
        developer="High Desert Digital Infrastructure",
        operator="Red Mesa Cloud Operations",
        state="TX",
        county="Williamson",
        lifecycle_state=LifecycleState.MONITORING_READY,
        announcement_date=date(2025, 9, 18),
        latest_update_date=date(2026, 3, 28),
        region_code="ERCOT",
        utility_name="Pedernales Electric Cooperative",
        phases=[
            {
                "phase_name": "Phase I",
                "phase_order": 1,
                "target_energization_date": date(2027, 6, 30),
                "modeled_primary_load_mw": 300,
                "optional_expansion_mw": 150,
            },
            {
                "phase_name": "Phase II",
                "phase_order": 2,
                "target_energization_date": date(2028, 3, 31),
                "modeled_primary_load_mw": 300,
                "optional_expansion_mw": 250,
            },
        ],
        project_stress_score=d("0.31"),
        regional_stress_score=d("0.22"),
        anomaly_score=d("0.07"),
        snapshot_features={
            "utility_identified": True,
            "power_path_identified": False,
            "new_transmission_required": True,
            "new_substation_required": True,
            "electrical_dependency_complexity_score": 4,
        },
        labels={"E2_label": True, "E3_intensity": d("0.10"), "E4_label": False},
        event_family=EventFamily.E2,
        event_scope=EventScope.PROJECT_PHASE,
        event_date=date(2026, 2, 14),
        reason_class="substation_timeline_slip",
        weak_label_weight=d("0.65"),
        event_notes="Demo example of a project-level disruption with power constraints mentioned but not strong enough for E1.",
    ),
    SeedProject(
        canonical_name="Blue Prairie AI Campus",
        developer="Frontier Runtime Partners",
        operator="Blue Prairie Hyperscale Services",
        state="TX",
        county="Ellis",
        lifecycle_state=LifecycleState.PRODUCTION_READY,
        announcement_date=date(2025, 5, 22),
        latest_update_date=date(2026, 4, 3),
        region_code="ERCOT",
        utility_name="Oncor Electric Delivery",
        phases=[
            {
                "phase_name": "Core Build",
                "phase_order": 1,
                "target_energization_date": date(2027, 9, 30),
                "modeled_primary_load_mw": 500,
                "optional_expansion_mw": 400,
            }
        ],
        project_stress_score=d("0.18"),
        regional_stress_score=d("0.19"),
        anomaly_score=d("0.03"),
        snapshot_features={
            "utility_identified": True,
            "power_path_identified": True,
            "new_transmission_required": False,
            "new_substation_required": True,
            "electrical_dependency_complexity_score": 2,
        },
        labels={"E2_label": False, "E3_intensity": d("0.05"), "E4_label": False},
    ),
    SeedProject(
        canonical_name="Cactus Flats Compute Hub",
        developer="Sonoran Grid Campus Partners",
        operator="Cactus Flats Cloud",
        state="AZ",
        county="Maricopa",
        lifecycle_state=LifecycleState.POWER_PATH_PARTIAL,
        announcement_date=date(2025, 11, 6),
        latest_update_date=date(2026, 3, 19),
        region_code="APS",
        utility_name="Arizona Public Service",
        phases=[
            {
                "phase_name": "Tranche A",
                "phase_order": 1,
                "target_energization_date": date(2027, 12, 31),
                "modeled_primary_load_mw": 900,
                "optional_expansion_mw": 300,
            }
        ],
        project_stress_score=d("0.42"),
        regional_stress_score=d("0.29"),
        anomaly_score=d("0.08"),
        snapshot_features={
            "utility_identified": True,
            "power_path_identified": True,
            "new_transmission_required": True,
            "new_substation_required": True,
            "electrical_dependency_complexity_score": 5,
        },
        labels={"E2_label": False, "E3_intensity": d("0.00"), "E4_label": True},
        event_family=EventFamily.E4,
        event_scope=EventScope.PROJECT_PHASE,
        event_date=date(2026, 1, 30),
        reason_class="onsite_generation_workaround",
        weak_label_weight=d("0.45"),
        event_notes="Demo example of workaround behavior suggesting latent power stress.",
    ),
    SeedProject(
        canonical_name="River Forge Data Park",
        developer="Allegheny Digital Buildco",
        operator="River Forge Colocation",
        state="VA",
        county="Prince William",
        lifecycle_state=LifecycleState.PHASE_RESOLVED,
        announcement_date=date(2025, 8, 12),
        latest_update_date=date(2026, 4, 5),
        region_code="PJM",
        utility_name="Dominion Energy Virginia",
        phases=[
            {
                "phase_name": "North Hall",
                "phase_order": 1,
                "target_energization_date": date(2027, 8, 31),
                "modeled_primary_load_mw": 300,
                "optional_expansion_mw": 100,
            },
            {
                "phase_name": "South Hall",
                "phase_order": 2,
                "target_energization_date": date(2028, 2, 29),
                "modeled_primary_load_mw": 500,
                "optional_expansion_mw": 200,
            },
        ],
        project_stress_score=d("0.24"),
        regional_stress_score=d("0.26"),
        anomaly_score=d("0.04"),
        snapshot_features={
            "utility_identified": True,
            "power_path_identified": True,
            "new_transmission_required": False,
            "new_substation_required": False,
            "electrical_dependency_complexity_score": 3,
        },
        labels={"E2_label": False, "E3_intensity": d("0.00"), "E4_label": False},
    ),
    SeedProject(
        canonical_name="Pine Harbor Compute Reserve",
        developer="Southeastern Capacity Ventures",
        operator="Pine Harbor Infrastructure Services",
        state="GA",
        county="Coweta",
        lifecycle_state=LifecycleState.LOAD_PARTIALLY_RESOLVED,
        announcement_date=date(2025, 10, 3),
        latest_update_date=date(2026, 2, 25),
        region_code="MISO-S",
        utility_name="Georgia Power Large Load Desk",
        phases=[
            {
                "phase_name": "Initial Block",
                "phase_order": 1,
                "target_energization_date": date(2027, 11, 30),
                "modeled_primary_load_mw": 500,
                "optional_expansion_mw": 500,
            }
        ],
        project_stress_score=d("0.27"),
        regional_stress_score=d("0.21"),
        anomaly_score=d("0.06"),
        snapshot_features={
            "utility_identified": False,
            "power_path_identified": False,
            "new_transmission_required": True,
            "new_substation_required": False,
            "electrical_dependency_complexity_score": 4,
        },
        labels={"E2_label": False, "E3_intensity": d("0.00"), "E4_label": False},
    ),
    SeedProject(
        canonical_name="Silver Butte AI Foundry",
        developer="Sierra Peak Digital Assets",
        operator="Silver Butte Inference Systems",
        state="NV",
        county="Storey",
        lifecycle_state=LifecycleState.NAMED_VERIFIED,
        announcement_date=date(2026, 1, 15),
        latest_update_date=date(2026, 4, 7),
        region_code="NVE",
        utility_name="NV Energy",
        phases=[
            {
                "phase_name": "Foundry Block A",
                "phase_order": 1,
                "target_energization_date": date(2028, 6, 30),
                "modeled_primary_load_mw": 1200,
                "optional_expansion_mw": 600,
            }
        ],
        project_stress_score=d("0.37"),
        regional_stress_score=d("0.24"),
        anomaly_score=d("0.09"),
        snapshot_features={
            "utility_identified": True,
            "power_path_identified": False,
            "new_transmission_required": True,
            "new_substation_required": True,
            "electrical_dependency_complexity_score": 5,
        },
        labels={"E2_label": False, "E3_intensity": d("0.00"), "E4_label": False},
    ),
]


def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def clear_existing_data(db: Session) -> None:
    for model in [
        StressObservation,
        StressScore,
        PhaseQuarterScore,
        ScoreRun,
        FieldProvenance,
        Claim,
        QuarterlySnapshot,
        QuarterlyLabel,
        ProjectPhaseQuarter,
        Event,
        Evidence,
        PhaseLoad,
        Phase,
        Project,
        Utility,
        Region,
    ]:
        db.execute(delete(model))
    db.flush()


def create_regions_and_utilities(db: Session) -> tuple[dict[str, Region], dict[str, Utility]]:
    regions: dict[str, Region] = {}
    for region_data in REGIONS:
        region = Region(**region_data)
        db.add(region)
        db.flush()
        regions[region.code or region.name] = region

    utilities: dict[str, Utility] = {}
    utility_to_region = {
        "Pedernales Electric Cooperative": "ERCOT",
        "Oncor Electric Delivery": "ERCOT",
        "Arizona Public Service": "APS",
        "Dominion Energy Virginia": "PJM",
        "Georgia Power Large Load Desk": "MISO-S",
        "NV Energy": "NVE",
    }
    for utility_name, region_code in utility_to_region.items():
        utility = Utility(name=utility_name, code=utility_name[:12].upper().replace(" ", "_"), region_id=regions[region_code].id)
        db.add(utility)
        db.flush()
        utilities[utility.name] = utility
    return regions, utilities


def create_evidence_claim(
    db: Session,
    *,
    evidence: Evidence,
    entity_type: str,
    entity_id,
    claim_type: str,
    claim_value_json: dict,
    claim_date: date,
    confidence: str,
    field_name: str | None = None,
) -> Claim:
    db.add(evidence)
    db.flush()
    claim = Claim(
        evidence_id=evidence.id,
        entity_type=entity_type,
        entity_id=entity_id,
        claim_type=claim_type,
        claim_value_json=claim_value_json,
        claim_date=claim_date,
        confidence=confidence,
        is_contradictory=False,
    )
    db.add(claim)
    db.flush()
    if field_name is not None:
        db.add(
            FieldProvenance(
                entity_type=entity_type,
                entity_id=entity_id,
                field_name=field_name,
                evidence_id=evidence.id,
                claim_id=claim.id,
            )
        )
    return claim


def seed_projects(db: Session, regions: dict[str, Region], utilities: dict[str, Utility]) -> list[Project]:
    seeded_projects: list[Project] = []
    current_quarter = date(2026, 4, 1)
    mock_scoring = MockScoringService()

    regional_e3_event = Event(
        event_family=EventFamily.E3.value,
        event_scope=EventScope.REGION.value,
        region_id=regions["ERCOT"].id,
        utility_id=utilities["Oncor Electric Delivery"].id,
        event_date=date(2026, 3, 11),
        severity="medium",
        reason_class="large_load_screening_update",
        confidence="high",
        evidence_class="official_notice",
        causal_strength=CausalStrength.EXPLICIT_SECONDARY.value,
        stress_direction=StressDirection.INCREASE.value,
        weak_label_weight=d("0.55"),
        adjudicated=True,
        notes="Demo regional stress action representing revised large-load screening criteria.",
    )
    db.add(regional_e3_event)
    db.flush()

    regional_e3_evidence = Evidence(
        source_type=SourceType.UTILITY_STATEMENT.value,
        source_date=date(2026, 3, 11),
        source_url="https://demo.local/ercot-large-load-guidance",
        source_rank=1,
        title="Demo ERCOT large-load screening guidance",
        extracted_text="Fake/demo notice describing tighter screening for very large loads.",
        reviewer_status=ReviewerStatus.REVIEWED.value,
    )
    db.add(regional_e3_evidence)
    db.flush()

    create_evidence_claim(
        db,
        evidence=regional_e3_evidence,
        entity_type="event",
        entity_id=regional_e3_event.id,
        claim_type="event_support",
        claim_value_json={"event_family": "E3", "reason_class": "large_load_screening_update"},
        claim_date=date(2026, 3, 11),
        confidence="high",
        field_name="event_family",
    )

    score_run = ScoreRun(
        run_type=ScoreRunType.MOCK_SCORING.value,
        snapshot_version="demo_q2_2026_v1",
        weight_config_version="demo_weights_v1",
        model_version="mock_v1",
        scoring_method="deterministic_weighted_stress",
        notes="Demo score run metadata used for local development.",
    )
    db.add(score_run)
    db.flush()

    for spec in PROJECTS:
        project = Project(
            canonical_name=spec.canonical_name,
            developer=spec.developer,
            operator=spec.operator,
            state=spec.state,
            county=spec.county,
            announcement_date=spec.announcement_date,
            latest_update_date=spec.latest_update_date,
            lifecycle_state=spec.lifecycle_state.value,
            region_id=regions[spec.region_code].id,
            utility_id=utilities[spec.utility_name].id,
        )
        db.add(project)
        db.flush()

        project_announcement_evidence = Evidence(
            source_type=SourceType.COUNTY_RECORD.value,
            source_date=spec.announcement_date,
            source_url=f"https://demo.local/projects/{project.id}/announcement",
            source_rank=2,
            title=f"Demo announcement record for {spec.canonical_name}",
            extracted_text=f"Fake/demo filing announcing {spec.canonical_name} in {spec.county} County with staged development plans.",
            reviewer_status=ReviewerStatus.REVIEWED.value,
        )
        create_evidence_claim(
            db,
            evidence=project_announcement_evidence,
            entity_type="project",
            entity_id=project.id,
            claim_type="project_announcement",
            claim_value_json={
                "canonical_name": spec.canonical_name,
                "announcement_date": spec.announcement_date.isoformat(),
            },
            claim_date=spec.announcement_date,
            confidence="high",
            field_name="canonical_name",
        )

        total_modeled_mw = Decimal("0")
        first_phase = None
        phase_quarter_rows: list[tuple[ProjectPhaseQuarter, QuarterlySnapshot, QuarterlyLabel]] = []
        for phase_spec in spec.phases:
            phase = Phase(
                project_id=project.id,
                phase_name=phase_spec["phase_name"],
                phase_order=phase_spec["phase_order"],
                announcement_date=spec.announcement_date,
                target_energization_date=phase_spec["target_energization_date"],
                status="active-planning",
                notes="Demo phase record for local backend testing.",
            )
            db.add(phase)
            db.flush()
            first_phase = first_phase or phase

            modeled_primary = Decimal(str(phase_spec["modeled_primary_load_mw"]))
            optional_expansion = Decimal(str(phase_spec["optional_expansion_mw"]))
            total_modeled_mw += modeled_primary

            db.add(
                PhaseLoad(
                    phase_id=phase.id,
                    load_kind=LoadKind.MODELED_PRIMARY.value,
                    load_mw=modeled_primary,
                    load_basis_type="modeled_primary_load_mw",
                    load_source="demo_seed",
                    load_confidence=d("0.90"),
                    is_optional_expansion=False,
                    is_firm=True,
                )
            )
            db.add(
                PhaseLoad(
                    phase_id=phase.id,
                    load_kind=LoadKind.OPTIONAL_EXPANSION.value,
                    load_mw=optional_expansion,
                    load_basis_type="optional_expansion_mw",
                    load_source="demo_seed",
                    load_confidence=d("0.70"),
                    is_optional_expansion=True,
                    is_firm=False,
                )
            )

            phase_load_evidence = Evidence(
                source_type=SourceType.DEVELOPER_STATEMENT.value,
                source_date=spec.latest_update_date,
                source_url=f"https://demo.local/phases/{phase.id}/load",
                source_rank=2,
                title=f"Demo load memo for {phase.phase_name}",
                extracted_text=f"Fake/demo statement describing {int(modeled_primary)} MW primary load and {int(optional_expansion)} MW optional expansion for {phase.phase_name}.",
                reviewer_status=ReviewerStatus.REVIEWED.value,
            )
            create_evidence_claim(
                db,
                evidence=phase_load_evidence,
                entity_type="phase",
                entity_id=phase.id,
                claim_type="phase_load_profile",
                claim_value_json={
                    "modeled_primary_load_mw": int(modeled_primary),
                    "optional_expansion_mw": int(optional_expansion),
                },
                claim_date=spec.latest_update_date,
                confidence="high",
                field_name="modeled_primary_load_mw",
            )

            ppq = ProjectPhaseQuarter(
                project_id=project.id,
                phase_id=phase.id,
                quarter=current_quarter,
                project_age_quarters=max(1, ((current_quarter.year - spec.announcement_date.year) * 4) + ((current_quarter.month - spec.announcement_date.month) // 3)),
                is_active=True,
                is_censored=False,
            )
            db.add(ppq)
            db.flush()

            snapshot = QuarterlySnapshot(
                project_phase_quarter_id=ppq.id,
                snapshot_version="demo_q2_2026_v1",
                feature_json={
                    **spec.snapshot_features,
                    "log_primary_mw": round(log(float(modeled_primary)), 4) if modeled_primary > 0 else 0.0,
                    "modeled_primary_load_mw": int(modeled_primary),
                    "project_age_quarters": ppq.project_age_quarters,
                    "region_code": spec.region_code,
                },
                observability_score=d("78.00"),
                data_quality_score=d("84.00"),
            )
            db.add(snapshot)
            db.flush()

            qlabel = QuarterlyLabel(
                project_phase_quarter_id=ppq.id,
                E1_label=False,
                E2_label=bool(spec.labels["E2_label"]),
                E3_intensity=spec.labels["E3_intensity"],
                E4_label=bool(spec.labels["E4_label"]),
                E1_label_confidence=d("0.00"),
                E2_label_confidence=d("0.82") if spec.labels["E2_label"] else d("0.00"),
                E3_confidence=d("0.88") if spec.region_code == "ERCOT" else d("0.30"),
                E4_label_confidence=d("0.76") if spec.labels["E4_label"] else d("0.00"),
                adjudication_status="reviewed_demo",
            )
            db.add(qlabel)
            db.flush()
            phase_quarter_rows.append((ppq, snapshot, qlabel))

        db.add(
            StressObservation(
                entity_type=StressEntityType.PROJECT.value,
                entity_id=project.id,
                region_id=regions[spec.region_code].id,
                utility_id=utilities[spec.utility_name].id,
                quarter=current_quarter,
                source_signal_type=SourceSignalType.FEATURE.value,
                signal_name="modeled_primary_load_mw",
                signal_value=total_modeled_mw,
                signal_weight=d("0.12"),
                source_ref_ids=[],
                derived_by="seed_demo_data",
                run_id="demo_seed_20260412",
            )
        )
        db.flush()

        project_stress_score = StressScore(
            entity_type=StressEntityType.PROJECT.value,
            entity_id=project.id,
            region_id=regions[spec.region_code].id,
            utility_id=utilities[spec.utility_name].id,
            quarter=current_quarter,
            project_stress_score=spec.project_stress_score,
            regional_stress_score=spec.regional_stress_score,
            anomaly_score=spec.anomaly_score,
            decomposition_json={
                "structural": float(spec.project_stress_score * d("0.50")),
                "weak_labels": float(spec.project_stress_score * d("0.30")),
                "regional": float(spec.regional_stress_score),
            },
            confidence_score=d("0.84"),
            model_version="mock_v1",
            run_id="demo_seed_20260412",
        )
        db.add(project_stress_score)
        db.flush()

        project_event = None
        if spec.event_family and first_phase:
            project_event = Event(
                event_family=spec.event_family.value,
                event_scope=spec.event_scope.value,
                project_id=project.id,
                phase_id=first_phase.id,
                region_id=regions[spec.region_code].id,
                utility_id=utilities[spec.utility_name].id,
                event_date=spec.event_date,
                severity="medium",
                reason_class=spec.reason_class,
                confidence="medium",
                evidence_class="demo_evidence",
                causal_strength=CausalStrength.IMPLIED.value,
                stress_direction=StressDirection.INCREASE.value,
                weak_label_weight=spec.weak_label_weight,
                adjudicated=True,
                notes=spec.event_notes,
            )
            db.add(project_event)
            db.flush()

            event_evidence = Evidence(
                source_type=SourceType.UTILITY_STATEMENT.value,
                source_date=spec.event_date,
                source_url=f"https://demo.local/events/{project_event.id}",
                source_rank=1,
                title=f"Demo event support for {spec.canonical_name}",
                extracted_text=f"Fake/demo statement supporting {spec.event_family.value} classification for {spec.canonical_name}: {spec.reason_class}.",
                reviewer_status=ReviewerStatus.REVIEWED.value,
            )
            create_evidence_claim(
                db,
                evidence=event_evidence,
                entity_type="event",
                entity_id=project_event.id,
                claim_type="event_support",
                claim_value_json={
                    "event_family": spec.event_family.value,
                    "reason_class": spec.reason_class,
                },
                claim_date=spec.event_date,
                confidence="medium",
                field_name="reason_class",
            )

        for phase_quarter, snapshot, label in phase_quarter_rows:
            score_response = mock_scoring.score_project(
                MockScoringInputs(
                    project=project,
                    phase_quarter=phase_quarter,
                    snapshot=snapshot,
                    labels=label,
                    stress_score=project_stress_score,
                )
            )
            db.add(
                PhaseQuarterScore(
                    project_phase_quarter_id=phase_quarter.id,
                    score_run_id=score_run.id,
                    deadline_date=score_response.deadline_date,
                    quarterly_hazard=d(str(score_response.current_hazard)),
                    deadline_probability=d(str(score_response.deadline_probability)),
                    top_contributors_json=[driver.model_dump() for driver in score_response.top_drivers],
                    graph_fragility_summary_json=score_response.graph_fragility_summary.model_dump(),
                    audit_trail_json={
                        "seed_source": "demo_seed_data",
                        "project_id": str(project.id),
                        "phase_id": str(phase_quarter.phase_id),
                        "event_id": str(project_event.id) if project_event else None,
                    },
                    scoring_notes="Deterministic demo score generated during seed reset.",
                    model_version=score_response.model_version,
                )
            )

        seeded_projects.append(project)

    db.add(
        StressScore(
            entity_type=StressEntityType.REGION.value,
            entity_id=regions["ERCOT"].id,
            region_id=regions["ERCOT"].id,
            utility_id=utilities["Oncor Electric Delivery"].id,
            quarter=date(2026, 4, 1),
            project_stress_score=d("0.00"),
            regional_stress_score=d("0.28"),
            anomaly_score=d("0.04"),
            decomposition_json={"policy_actions": 0.16, "queue_pressure": 0.12},
            confidence_score=d("0.86"),
            model_version="mock_v1",
            run_id="demo_seed_20260412",
        )
    )

    return seeded_projects


def seed(reset: bool) -> None:
    if reset:
        reset_database()
    else:
        create_db_and_tables()

    with SessionLocal() as db:
        clear_existing_data(db)
        regions, utilities = create_regions_and_utilities(db)
        seed_projects(db, regions, utilities)
        db.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset and seed deterministic demo data.")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate tables before seeding.")
    args = parser.parse_args()
    seed(reset=args.reset)
    print("Demo seed complete.")


if __name__ == "__main__":
    main()
