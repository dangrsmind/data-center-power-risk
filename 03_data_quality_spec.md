# Data Quality Specification (v1)

## Purpose
Define how project data is collected, normalized, adjudicated, and validated so it can support forecasting and audit.

The goal is NOT just data collection. The goal is:
- consistent entity resolution
- clear load definitions
- traceable evidence
- reliable event labeling
- reproducible time-series snapshots

---

## Core Principles

1. Evidence before inference  
   Store what sources say before interpreting.

2. Separate objects  
   Keep:
   - projects
   - phases
   - evidence
   - claims
   - events  
   as distinct entities.

3. Explicit ambiguity  
   Do not force unclear cases into yes/no labels.

4. Provenance required  
   Every important field must link to source evidence.

5. Quality is measurable  
   Each project-phase must have a quality score.

---

## Data Objects

### Projects
- campus-level concept

### Phases
- separately timed / powered units

### Evidence
- documents, filings, press, records

### Claims
- extracted facts from evidence

### Events
- adjudicated status changes

### Quarterly Snapshots
- model-ready records

---

## Required Fields

### Identity
- project_id
- phase_id
- canonical_name
- aliases
- developer
- operator
- state / county / location
- utility
- RTO/ISO

---

### Load Fields
- headline_load_mw
- modeled_primary_load_mw
- optional_expansion_mw
- load_basis_type
- load_source
- load_confidence

RULE:
- NEVER merge optional expansion into primary load unless explicitly firm

---

### Timing Fields
- announcement_date
- target_energization_date
- latest_update_date

---

### Power Path Fields
- utility_identified
- power_path_identified
- service_type_known
- interconnection_status_known
- new_transmission_required
- new_substation_required
- new_generation_required
- onsite_generation_flag
- non_firm_or_novel_service_flag

---

### Evidence Fields
- source_type
- source_date
- source_url
- source_rank
- extracted_text
- reviewer_status

---

## Event Labeling

### Label Types

- E1: strict qualifying event  
- E2: project disruption (weaker evidence)  
- E3: system/regulatory stress  
- E4: workaround behavior  

---

### Event Fields
- event_type (E1–E4)
- event_date
- severity
- reason_class
- confidence
- evidence_class
- adjudicated (true/false)

---

### Label Rules

E1 requires:
- named project
- clear delay/downsize/cancel
- power/interconnection as PRIMARY cause

E2:
- disruption + power mention
- but not strong enough for E1

E3:
- utility/RTO/system action

E4:
- workaround behavior

---

## Lifecycle States

Each project-phase moves through:

- candidate_unverified
- named_verified
- location_verified
- load_resolved
- phase_resolved
- power_path_partial
- monitoring_ready
- production_ready

---

## Production-Ready Requirements

A record is production-ready only if it has:

- resolved identity
- modeled_primary_load_mw
- at least one timing source
- power-path info OR explicit unknown
- evidence links for key fields
- human-reviewed critical fields

---

## Data Quality Score (0–100)

### Identity (0–20)
- naming, location, developer clarity

### Load (0–20)
- primary load defined and sourced

### Timing (0–15)
- dates known and current

### Power Path (0–20)
- dependencies identified

### Evidence (0–15)
- multiple sources, recent

### Labels (0–10)
- adjudicated events

Production threshold: **>= 75**

---

## Contradiction Handling

- never overwrite conflicting data
- store multiple claims
- mark contradictions
- resolve via reviewer notes

---

## Gold Set

Create a manually reviewed dataset with:
- clean positives
- ambiguous cases
- negatives
- contradictions

Used for:
- training
- validation
- calibration

---

## Automation vs Human

### Automate
- text extraction
- source classification
- MW detection
- date detection

### Human required
- primary load decisions
- phase splitting
- E1 labeling
- cause attribution

---

## Snapshot Construction

For each quarter:
- build project-phase record
- include:
  - features
  - labels
  - evidence counts
  - stress signals (later)

Snapshots must be versioned.

---

## Success Criteria

The dataset is successful if:
- each record is traceable to sources
- ambiguity is preserved, not hidden
- labels are consistent
- time-series is reproducible
- model can train without data confusion