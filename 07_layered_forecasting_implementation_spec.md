# Layered Forecasting Implementation Spec

**System:** Power-linked impairment forecasting for large U.S. data-center projects
**Version:** Draft v2 implementation spec
**Purpose:** Translate the revised layered modeling architecture into an implementation-ready backend specification for engineering.

## 1. Problem framing

The strict public forecast target remains unchanged:

> Will at least one announced U.S. data-center project in the United States with planned load of at least 300 MW be publicly delayed, downsized, or canceled on or before December 31, 2026, with power access, grid interconnection, or electrical-infrastructure constraints identified as a primary reason?

The strict event target is too sparse to serve as the only training label. The implementation must therefore support a layered architecture in which strict labels are preserved for the external forecast contract, while broader weak labels and stress signals drive the first operational model. This is consistent with the first-pass adjudication finding of zero confirmed qualifying strict positives in the starter set. fileciteturn0file2

## 2. Layered architecture

### Layer A — Strict settlement event model

Purpose:

* preserve the public forecast contract
* estimate auditable probability of the strict event E1

Event type:

* E1 = strict qualifying project-level delay, downsizing, or cancellation caused primarily by power access, interconnection, or electrical-infrastructure constraints

Recommended output:

* quarter-level hazard for E1
* cumulative probability of E1 by specified deadline

### Layer B — Weak event family

Purpose:

* capture broader evidence of stress and slippage when E1 is too sparse

Event types:

* E2 = broader project-level timeline disruption where power/interconnection/electrical evidence is mentioned but not strong enough for E1
* E3 = utility/regulatory stress actions affecting large loads
* E4 = workaround behavior indicating latent power stress

Recommended output:

* per-project and per-region weak-label signals
* event counts, confidence, and intensity metrics

### Layer C — Latent stress model

Purpose:

* estimate project-level and region-level stress states using structural features plus E2–E4 signals

Recommended output:

* project stress score
* regional stress score
* stress decomposition by signal family

### Layer D — Mapping layer

Purpose:

* convert latent stress plus structural features into an auditable probability for E1

Recommended output:

* calibrated E1 probability
* explanation trail linking E2–E4 evidence to E1 forecast

## 3. Event ontology

### E1 — Strict qualifying event

Definition:
A named project or phase is publicly delayed, downsized, or canceled, and power access, interconnection, or electrical infrastructure is identified as a primary cause.

Adjudication requirements:

* named project or phase
* public evidence of delay, downsize, or cancel
* explicit primary power/interconnection/electrical causation
* evidence meets source-confidence threshold

### E2 — Power-linked disruption

Definition:
A named project or phase shows timeline or scope disruption, and power/interconnection/electrical issues are mentioned or strongly implied, but the evidence is insufficient for E1.

Adjudication requirements:

* named project or phase
* timeline or scope movement
* power-related mention or credible implication
* insufficient causal certainty or insufficient source strength for E1

### E3 — System stress action

Definition:
A utility, RTO, regulator, or other institutional actor takes action affecting large-load service, treatment, or interconnection in a way that signals stress.

Examples:

* hookup pauses
* flexible-load treatment
* special tariffs
* queue restrictions
* cost allocation changes
* curtailment frameworks

Unit of analysis:

* region, RTO, utility territory, county cluster, or other institutional scope

### E4 — Workaround / adaptation

Definition:
A project adopts behavior that suggests latent power stress rather than unconstrained access.

Examples:

* onsite generation
* staged energization
* behind-the-meter workaround
* explicit flexible-load architecture
* power-path complexity introduced to overcome constraints

## 4. Required schema changes

The existing schema must be extended to support multi-label events and stress-state estimation.

### 4.1 Events table additions

Required fields:

* event_family (`E1`, `E2`, `E3`, `E4`)
* event_scope (`project_phase`, `project`, `utility`, `county`, `region`, `RTO`)
* event_confidence
* causal_strength (`explicit_primary`, `explicit_secondary`, `implied`, `unknown`)
* stress_direction (`increase`, `decrease`, `neutral`)
* weak_label_weight

### 4.2 Stress observations table

Create a new table: `stress_observations`

Fields:

* stress_obs_id
* entity_type (`project_phase`, `project`, `utility`, `county`, `region`, `RTO`)
* entity_id
* quarter
* source_signal_type (`feature`, `E2`, `E3`, `E4`, `anomaly`)
* signal_name
* signal_value
* signal_weight
* source_ref_ids
* derived_by
* run_id

### 4.3 Stress scores table

Create a new table: `stress_scores`

Fields:

* stress_score_id
* entity_type
* entity_id
* quarter
* project_stress_score
* regional_stress_score
* anomaly_score
* decomposition_json
* confidence_score
* model_version
* run_id

### 4.4 Quarterly labels table

Create or extend a table for quarter-level labels:

* phase_id
* quarter
* E1_label
* E2_label
* E3_intensity
* E4_label
* E1_label_confidence
* E2_label_confidence
* E3_confidence
* E4_label_confidence
* adjudication_status

## 5. Feature engineering specification

### 5.1 Project-level structural features

* modeled_primary_load_mw
* headline_load_mw
* optional_expansion_mw
* first-firm-tranche flag
* project age in quarters
* announce year
* timeline aggressiveness score
* phase count
* phase concentration score

### 5.2 Power-path features

* utility identified
* power path identified
* service type known
* interconnection status known
* new transmission required
* new substation required
* new generation required
* storage dependency present
* transformer constraint signal
* switchgear constraint signal
* onsite generation planned
* behind-the-meter flag
* staged energization flag
* novel service or non-firm flag

### 5.3 Evidence / disclosure features

* official update count trailing 2 quarters
* credible update count trailing 2 quarters
* power-constraint term count trailing 2 quarters
* contradiction count trailing 4 quarters
* observability score
* power-path confidence score

### 5.4 Region / institutional stress features

* adequacy stress indicator
* reserve-margin stress signal
* large-load backlog signal
* utility large-load policy actions
* interconnection/tariff novelty score
* cost allocation action flag
* county/local cluster saturation score
* local transmission stress proxy

### 5.5 Weak-label features

* E2 count trailing 4 quarters
* E2 weighted severity score
* E3 regional intensity trailing 4 quarters
* E4 workaround count
* E4 workaround complexity score

### 5.6 Anomaly features

* project anomaly score vs peer projects
* region anomaly score vs peer regions
* sudden change flags in timeline, dependency complexity, or event intensity

## 6. Model stack recommendation

### 6.1 Layer B — Weak event classifiers

Implement event-family classifiers or rules-assisted classifiers for E2, E3, and E4.

Recommended v1 approach:

* rules + human review for event detection
* structured confidence weights
* optional ML classifier after a gold set exists

### 6.2 Layer C — Latent stress model

Recommended v1 approach:

* hybrid additive stress model
* partially weighted score using structural features + weak-label signals + anomaly score

Implementation form:
[
S_{i,t} = w_1 X^{project}*{i,t} + w_2 X^{powerpath}*{i,t} + w_3 E2_{i,t} + w_4 E4_{i,t} + w_5 A_{i,t} + w_6 R_{r,t}
]

Where:

* (S_{i,t}) = project stress score
* (R_{r,t}) = region-level stress score
* (A_{i,t}) = anomaly input

Recommended v2 approach:

* Bayesian hierarchical latent-state model with partial pooling by utility, region, and power-path archetype

### 6.3 Layer D — E1 forecast mapping

Recommended v1 approach:

* discrete-time hazard model for E1 using stress scores plus structural features

Implementation form:
[
\text{logit}(h_{i,t}^{E1}) = \alpha_{age(i,t)} + \gamma_{calendar(t)} + \beta^\top X_{i,t-1} + \theta_1 S_{i,t-1} + \theta_2 R_{r,t-1}
]

Where:

* (h_{i,t}^{E1}) = quarterly hazard for the strict E1 event
* (S_{i,t-1}) = lagged project stress score
* (R_{r,t-1}) = lagged regional stress score

Cumulative probability by deadline:
[
P(E1_i \text{ by } T) = 1 - \prod_{t \le T}(1 - h_{i,t}^{E1})
]

## 7. Weak-label and strict-label adjudication rules

### 7.1 General rules

* all E1 positives require human review
* all E2 near-positives require human review
* E3 events may be semi-automated but should support reviewer confirmation
* E4 events may be semi-automated but must preserve source evidence and rationale

### 7.2 Confidence policy

Suggested confidence tiers:

* high = official filing or direct utility/regulatory confirmation
* medium = official local record or direct developer statement with concrete language
* low = credible press or indirect wording

### 7.3 Weight policy

Suggested default weak-label weights:

* E1 = 1.0
* E2 = 0.5 to 0.8 depending on confidence and causal strength
* E3 = 0.2 to 0.7 depending on scope and proximity to project geography
* E4 = 0.2 to 0.6 depending on workaround strength and evidence quality

These weights should be configurable and versioned.

## 8. Pipeline design

### 8.1 Ingestion pipeline

* ingest documents and structured records
* assign source family and source rank
* store provenance

### 8.2 Extraction pipeline

* extract projects, phases, load claims, timeline claims, power-path claims, and event language
* store claims separately from normalized values

### 8.3 Adjudication pipeline

* reviewer resolves project identity, phase, load basis, event family, confidence, and reason class
* reviewer resolves contradictions

### 8.4 Quarterly assembly pipeline

For each quarter:

* build project-phase-quarter snapshot
* assemble region-level signals
* attach E2/E3/E4 labels and intensities
* compute anomaly features
* compute stress scores
* compute E1 hazard and cumulative deadline probability

### 8.5 Scoring pipeline

Per run:

* version data snapshot
* version weak-label configuration
* version stress weights
* version E1 mapping model
* store score outputs and decomposition

## 9. API requirements

Add or extend backend endpoints to expose the layered system.

Required endpoints:

* `GET /projects`
* `GET /projects/{id}`
* `GET /projects/{id}/phases`
* `GET /projects/{id}/evidence`
* `GET /projects/{id}/events`
* `GET /projects/{id}/stress`
* `GET /projects/{id}/score`
* `GET /projects/{id}/history`
* `GET /regions/{id}/stress`
* `GET /queue/adjudication`
* `POST /adjudications`
* `GET /data-quality`

### 9.1 Score response object

Include:

* current E1 quarterly hazard
* cumulative E1 probability by deadline
* project stress score
* regional stress score
* anomaly score
* top contributing signals
* E2/E3/E4 evidence summary
* evidence quality score
* audit trail

## 10. UI requirements impact

The UI must now support more than a single score.

Minimum required analyst views:

* strict E1 score card
* stress decomposition panel
* weak-event evidence panel for E2/E3/E4
* regional stress context panel
* adjudication queue filtered by event family
* history panel showing how stress and E1 probability changed over time

## 11. Validation design

### 11.1 E1 validation

* rolling-origin temporal backtests
* event recall at 1–4 quarter lead times
* calibration
* Brier score

### 11.2 Weak-label validation

* adjudicator agreement
* precision / recall on gold-set E2/E3/E4 labels
* contradiction resolution accuracy

### 11.3 Stress-model validation

* correlation of stress scores with subsequent E2 and E1 emergence
* stability across regions and utilities
* analyst face-validity review

### 11.4 Anomaly validation

* whether high anomaly scores identify projects/regions later adjudicated as E2 or E1 candidates
* anomaly layer should be treated as supporting evidence, not final output

## 12. Build order for engineering

### Phase 1

* extend schema for E1–E4
* add stress observations and stress scores tables
* extend adjudication workflow
* preserve current E1 model pathway

### Phase 2

* implement E2/E3/E4 event storage and scoring
* implement region-level aggregation pipeline
* implement v1 additive stress model

### Phase 3

* implement E1 hazard model using stress inputs
* add history and decomposition endpoints
* expose layered outputs in API

### Phase 4

* add anomaly detection support
* add configurable weights and calibration layer
* improve UI for layered outputs

## 13. Critical constraints

* strict E1 remains the external forecast contract
* do not train only on E1 yes/no labels
* do not collapse weak labels into strict labels
* maintain full provenance for all signal inputs
* version all derived scores and weights
* keep optional expansion separate from modeled primary load by default

## 14. Definition of success

Success means the implemented system can:

* preserve the strict external forecast question
* capture broader evidence of power-linked stress below the surface
* estimate project and regional stress in a structured, explainable way
* map that stress into an auditable forecast probability for the strict public event
* show analysts why the score changed and which evidence drove the update

## 15. Codex-safe implementation block

Use this exact implementation summary when handing off to engineering:

Implement the forecasting backend as a layered system with four layers: E1 strict event model, E2/E3/E4 weak-event family, latent stress model, and E1 probability mapping layer. Extend the schema to store weak labels, stress observations, and stress scores. Keep `project_phase_quarter` as the core time unit. Preserve the strict E1 event as the external forecast target, but do not train only on E1 yes/no labels. Implement quarter-level storage for E1, E2, E3, and E4 labels or intensities. Compute project and regional stress scores from structural features, power-path features, weak labels, and anomaly signals. Then use a discrete-time hazard model to convert lagged stress scores plus structural features into the quarter-level probability of E1. Store decomposition, confidence, provenance, and score history for every run. Keep optional expansion separate from modeled primary load unless explicitly firm. All E1 positives and E2 near-positives must remain human-reviewed.
