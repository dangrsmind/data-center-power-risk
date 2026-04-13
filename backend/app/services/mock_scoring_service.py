from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from app.models.project import Project
from app.models.quarterly import ProjectPhaseQuarter, QuarterlyLabel, QuarterlySnapshot, StressScore
from app.schemas.score import GraphFragilitySummary, ProjectScoreResponse, ScoreDriver


def _d(value: float | int | str | Decimal) -> Decimal:
    return Decimal(str(value))


def _clamp(value: Decimal, lower: Decimal, upper: Decimal) -> Decimal:
    return max(lower, min(value, upper))


def _q6(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _json_number(value: Decimal) -> float:
    return float(value)


@dataclass
class MockScoringInputs:
    project: Project
    phase_quarter: ProjectPhaseQuarter | None
    snapshot: QuarterlySnapshot | None
    labels: QuarterlyLabel | None
    stress_score: StressScore | None


class MockScoringService:
    MODEL_VERSION = "mock_v1"
    SCORING_METHOD = "deterministic_weighted_stress"

    def score_project(self, inputs: MockScoringInputs) -> ProjectScoreResponse:
        feature_json = inputs.snapshot.feature_json if inputs.snapshot and isinstance(inputs.snapshot.feature_json, dict) else {}

        project_stress = _d(inputs.stress_score.project_stress_score or 0) if inputs.stress_score else _d(0.18)
        regional_stress = _d(inputs.stress_score.regional_stress_score or 0) if inputs.stress_score else _d(0.12)
        anomaly_score = _d(inputs.stress_score.anomaly_score or 0) if inputs.stress_score else _d(0.05)
        evidence_quality = _d(inputs.snapshot.data_quality_score or 60) / _d(100) if inputs.snapshot else _d(0.60)
        observability = _d(inputs.snapshot.observability_score or 55) / _d(100) if inputs.snapshot else _d(0.55)

        e2_weight = _d(0.16) if inputs.labels and inputs.labels.E2_label else _d(0)
        e3_weight = _d(inputs.labels.E3_intensity or 0) * _d("0.08") if inputs.labels else _d(0)
        e4_weight = _d(0.10) if inputs.labels and inputs.labels.E4_label else _d(0)

        complexity = _d(feature_json.get("electrical_dependency_complexity_score", 0)) * _d("0.05")
        path_unidentified = _d("0.12") if feature_json.get("power_path_identified") is False else _d(0)
        utility_unidentified = _d("0.08") if feature_json.get("utility_identified") is False else _d(0)
        new_transmission = _d("0.10") if feature_json.get("new_transmission_required") else _d(0)
        new_substation = _d("0.06") if feature_json.get("new_substation_required") else _d(0)

        base = _d("0.02")
        hazard = _clamp(
            base
            + project_stress * _d("0.35")
            + regional_stress * _d("0.20")
            + anomaly_score * _d("0.10")
            + e2_weight
            + e3_weight
            + e4_weight
            + complexity
            + path_unidentified
            + utility_unidentified
            + new_transmission
            + new_substation
            - evidence_quality * _d("0.05")
            - observability * _d("0.03"),
            _d("0.01"),
            _d("0.95"),
        )

        deadline_probability = _clamp(
            hazard * _d("2.8") + project_stress * _d("0.25") + regional_stress * _d("0.15"),
            hazard,
            _d("0.99"),
        )

        drivers = [
            ("project stress score", project_stress * _d("0.35")),
            ("regional stress score", regional_stress * _d("0.20")),
            ("E2 weak label", e2_weight),
            ("E3 intensity", e3_weight),
            ("E4 workaround flag", e4_weight),
            ("power path not identified", path_unidentified),
            ("utility not identified", utility_unidentified),
            ("new transmission required", new_transmission),
            ("new substation required", new_substation),
            ("dependency complexity", complexity),
        ]
        top_drivers = [
            ScoreDriver(signal=name, contribution=_json_number(_q4(contribution)))
            for name, contribution in sorted(drivers, key=lambda item: item[1], reverse=True)
            if contribution > 0
        ][:3]

        return ProjectScoreResponse(
            project_id=inputs.project.id,
            phase_id=inputs.phase_quarter.phase_id if inputs.phase_quarter else None,
            quarter=inputs.phase_quarter.quarter if inputs.phase_quarter else None,
            deadline_date=date(2026, 12, 31),
            current_hazard=_json_number(_q6(hazard)),
            deadline_probability=_json_number(_q6(deadline_probability)),
            project_stress_score=_json_number(_q4(project_stress)),
            regional_stress_score=_json_number(_q4(regional_stress)),
            anomaly_score=_json_number(_q4(anomaly_score)),
            evidence_quality_score=_json_number(_q4(evidence_quality)),
            model_version=self.MODEL_VERSION,
            scoring_method=self.SCORING_METHOD,
            top_drivers=top_drivers,
            weak_signal_summary={
                "E2_label": inputs.labels.E2_label if inputs.labels else False,
                "E3_intensity": _json_number(_q4(_d(inputs.labels.E3_intensity or 0)))
                if inputs.labels
                else _json_number(_q4(_d(0))),
                "E4_label": inputs.labels.E4_label if inputs.labels else False,
            },
            graph_fragility_summary=GraphFragilitySummary(
                most_likely_break_node="transmission_upgrade" if new_transmission > 0 else "substation_capacity",
                unresolved_critical_nodes=int(
                    (1 if path_unidentified > 0 else 0)
                    + (1 if new_transmission > 0 else 0)
                    + (1 if new_substation > 0 else 0)
                ),
            ),
        )
