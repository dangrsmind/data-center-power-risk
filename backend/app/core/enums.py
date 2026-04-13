from enum import Enum


def enum_values(enum_cls: type[Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class LifecycleState(str, Enum):
    CANDIDATE_UNVERIFIED = "candidate_unverified"
    NAMED_VERIFIED = "named_verified"
    LOCATION_VERIFIED = "location_verified"
    LOAD_PARTIALLY_RESOLVED = "load_partially_resolved"
    PHASE_RESOLVED = "phase_resolved"
    POWER_PATH_PARTIAL = "power_path_partial"
    MONITORING_READY = "monitoring_ready"
    PRODUCTION_READY = "production_ready"


class SourceType(str, Enum):
    OFFICIAL_FILING = "official_filing"
    UTILITY_STATEMENT = "utility_statement"
    REGULATORY_RECORD = "regulatory_record"
    COUNTY_RECORD = "county_record"
    PRESS = "press"
    DEVELOPER_STATEMENT = "developer_statement"
    OTHER = "other"


class ReviewerStatus(str, Enum):
    PENDING = "pending"
    REVIEWED = "reviewed"
    REJECTED = "rejected"


class ClaimEntityType(str, Enum):
    PROJECT = "project"
    PHASE = "phase"
    EVENT = "event"
    REGION = "region"
    UTILITY = "utility"
    EVIDENCE = "evidence"


class EventFamily(str, Enum):
    E1 = "E1"
    E2 = "E2"
    E3 = "E3"
    E4 = "E4"


class EventScope(str, Enum):
    PROJECT_PHASE = "project_phase"
    PROJECT = "project"
    UTILITY = "utility"
    COUNTY = "county"
    REGION = "region"
    RTO = "RTO"


class CausalStrength(str, Enum):
    EXPLICIT_PRIMARY = "explicit_primary"
    EXPLICIT_SECONDARY = "explicit_secondary"
    IMPLIED = "implied"
    UNKNOWN = "unknown"


class StressDirection(str, Enum):
    INCREASE = "increase"
    DECREASE = "decrease"
    NEUTRAL = "neutral"


class AdjudicationStatus(str, Enum):
    QUALIFYING_POSITIVE = "qualifying_positive"
    AMBIGUOUS_NEAR_POSITIVE = "ambiguous_near_positive"
    NON_EVENT = "non_event"


class LoadKind(str, Enum):
    HEADLINE = "headline"
    MODELED_PRIMARY = "modeled_primary"
    OPTIONAL_EXPANSION = "optional_expansion"


class StressEntityType(str, Enum):
    PROJECT_PHASE = "project_phase"
    PROJECT = "project"
    UTILITY = "utility"
    COUNTY = "county"
    REGION = "region"
    RTO = "RTO"


class SourceSignalType(str, Enum):
    FEATURE = "feature"
    E2 = "E2"
    E3 = "E3"
    E4 = "E4"
    ANOMALY = "anomaly"


class ScoreRunType(str, Enum):
    SNAPSHOT = "snapshot"
    MOCK_SCORING = "mock_scoring"
