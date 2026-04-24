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


class ClaimType(str, Enum):
    PROJECT_NAME_MENTION = "project_name_mention"
    PHASE_NAME_MENTION = "phase_name_mention"
    DEVELOPER_NAMED = "developer_named"
    OPERATOR_NAMED = "operator_named"
    LOCATION_STATE = "location_state"
    LOCATION_COUNTY = "location_county"
    UTILITY_NAMED = "utility_named"
    REGION_OR_RTO_NAMED = "region_or_rto_named"
    MODELED_LOAD_MW = "modeled_load_mw"
    OPTIONAL_EXPANSION_MW = "optional_expansion_mw"
    ANNOUNCEMENT_DATE = "announcement_date"
    TARGET_ENERGIZATION_DATE = "target_energization_date"
    LATEST_UPDATE_DATE = "latest_update_date"
    POWER_PATH_IDENTIFIED_FLAG = "power_path_identified_flag"
    NEW_TRANSMISSION_REQUIRED_FLAG = "new_transmission_required_flag"
    NEW_SUBSTATION_REQUIRED_FLAG = "new_substation_required_flag"
    ONSITE_GENERATION_FLAG = "onsite_generation_flag"
    TIMELINE_DISRUPTION_SIGNAL = "timeline_disruption_signal"
    EVENT_SUPPORT_E2 = "event_support_e2"
    EVENT_SUPPORT_E3 = "event_support_e3"
    EVENT_SUPPORT_E4 = "event_support_e4"


class ClaimReviewStatus(str, Enum):
    UNREVIEWED = "unreviewed"
    LINKED = "linked"
    ACCEPTED_CANDIDATE = "accepted_candidate"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    AMBIGUOUS = "ambiguous"
    NEEDS_MORE_REVIEW = "needs_more_review"


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
