Absolutely — here is the **full Operator Manual as one single `.md` file**, with no omissions and no interruptions.

Copy **everything inside the code block** and paste it directly into:

```text
docs/04_operator_manual.md
```

````markdown
# Operator Manual v1 — Data Center Power Risk System

## 1. Purpose

This manual explains how to operate the Data Center Power Risk System as an analyst.

The system is designed to:
- ingest real-world source material
- extract structured claims
- link claims to projects or phases
- adjudicate claims
- update normalized system fields with full provenance
- preserve uncertainty and contradictions rather than overwriting them

The goal is not speed. The goal is **traceable, auditable truth**.

This system is not a generic note-taking tool or a normal CRUD application. It is an evidence-based forecasting and adjudication system. Every accepted fact should be traceable to a specific source through an explicit analyst workflow.

---

## 2. Core Concepts

Before operating the system, understand the core objects.

### Evidence
A source document or source excerpt, such as:
- a utility filing
- a county planning record
- a regulatory filing
- a developer statement
- a local business press item

Evidence represents:

> “This source says something.”

Evidence is intentionally created **before** project identity is fully resolved.

---

### Claim
A single extracted fact from evidence.

Examples:
- project name mentioned
- developer named
- county named
- modeled load stated
- target energization date stated

A claim represents:

> “The source says this specific thing.”

Claims are created before they are linked, reviewed, or accepted.

---

### Linking
Assigning a claim to the entity it belongs to:
- project
- phase

Linking represents:

> “This claim refers to this project or phase.”

Linking is separate from review and acceptance.

---

### Review
Analyst judgment about whether a linked claim is usable.

Review represents:

> “Do we trust this enough to consider accepting it?”

Possible outcomes include:
- accepted_candidate
- rejected
- ambiguous
- needs_more_review

Review does **not** itself update normalized system fields.

---

### Acceptance
Committing a reviewed claim into a normalized system field.

Acceptance represents:

> “We now treat this as current structured system truth.”

Acceptance:
- updates a normalized field
- records provenance
- preserves older claims rather than deleting them

---

### Provenance
The audit trail connecting:
- normalized field
- claim
- evidence
- source

Provenance answers:

> “Why does the system believe this field is true?”

If provenance is missing, trust is broken.

---

### Project
A named data center campus or project record tracked by the system.

Projects are the main entity shown in the project list and detail pages.

---

### Phase
A timed or scoped subdivision of a project.

Phases may have their own:
- load values
- timing
- power-path dependencies
- evidence
- risk

---

### Events
Structured disruption or signal records such as:
- E1 strict event
- E2 project disruption
- E3 system/regulatory stress
- E4 workaround behavior

Events are part of the layered forecasting system.

---

### Stress
A structured score and signal layer representing project or regional power constraint pressure.

Stress is not the same thing as a final impairment event. It is part of the system’s reasoning about why risk exists.

---

## 3. System Principles

The system is designed around these principles:

1. **Evidence before inference**  
   First record what the source says. Do not jump straight to normalized truth.

2. **Claims before acceptance**  
   Extract facts as claims first. Only later decide what should be accepted.

3. **Linkage before review**  
   A claim should be assigned to the correct project or phase before it is reviewed for acceptance.

4. **Review before acceptance**  
   Nothing should become normalized system truth without analyst review.

5. **Contradictions are preserved**  
   Conflicting claims are stored as parallel records. They are not silently overwritten.

6. **Provenance is mandatory**  
   Accepted facts must be traceable.

7. **Uncertainty is allowed**  
   If a fact is ambiguous, leave it unresolved or mark it ambiguous.

---

## 4. The Core Ingestion Workflow

Always follow this sequence:

```text
Evidence → Claims → Link → Review → Accept → Verify
````

Never skip steps.

Do not:

* create claims without evidence
* review claims before linking
* accept claims before review
* force unclear claims into accepted state

---

## 5. Where to Operate the System

Manual ingestion and adjudication are currently performed through the API docs:

```text
http://127.0.0.1:8000/docs
```

This is the operator work surface for ingestion until a dedicated ingestion UI exists.

The Replit-built frontend is currently for:

* project browsing
* risk inspection
* events/stress/history/evidence viewing

It is **not yet** the main ingestion interface.

---

## 6. Required IDs and What They Mean

One of the biggest operator mistakes is mixing up IDs.

### evidence_id

Identifies a source record.

Use it for:

* creating claims from evidence
* inspecting evidence detail

### claim_id

Identifies one extracted fact.

Use it for:

* linking
* reviewing
* accepting

### project_id

Identifies a project.

Use it for:

* linking project-level claims
* viewing project evidence
* viewing project detail

### phase_id

Identifies a phase.

Use it for:

* linking phase-level claims
* inspecting phase-specific data

### Rule

Use the right ID in the right endpoint.

Do not substitute:

* evidence_id where project_id is expected
* project_id where evidence_id is expected
* claim_id where evidence_id is expected

---

## 7. Step-by-Step Operator Workflow

### Step 1 — Create Evidence

**Endpoint**

```text
POST /evidence
```

**Purpose**
Record a raw source document or source excerpt.

**What to enter**

* source_type
* source_date
* source_url
* source_rank
* title
* extracted_text
* reviewer_status

**Typical source_type values**

* official_filing
* utility_statement
* developer_statement
* county_record
* regulatory_record
* press
* other

**Output**

* evidence_id
* created_at
* updated_at
* next_action

**Example**

```json
{
  "source_type": "developer_statement",
  "source_date": "2026-04-16",
  "source_url": "https://example.com/pilot-source",
  "source_rank": 1,
  "title": "Pilot Source for Blue Prairie",
  "extracted_text": "Blue Prairie AI Campus, developed by Frontier Runtime Partners, is located in Ellis County, Texas.",
  "reviewer_status": "pending"
}
```

**What success looks like**

* response returns a valid evidence_id
* response includes next_action such as `create_claims`

---

### Step 2 — Create Claims from Evidence

**Endpoint**

```text
POST /evidence/{evidence_id}/claims
```

**Purpose**
Extract specific facts from the evidence.

**Typical pilot claim types**

* project_name_mention
* developer_named
* location_state
* location_county
* modeled_load_mw
* target_energization_date

**Example**

```json
{
  "claims": [
    {
      "claim_type": "project_name_mention",
      "claim_value": {
        "project_name": "Blue Prairie AI Campus"
      },
      "confidence": "high"
    },
    {
      "claim_type": "developer_named",
      "claim_value": {
        "developer_name": "Frontier Runtime Partners"
      },
      "confidence": "high"
    },
    {
      "claim_type": "location_state",
      "claim_value": {
        "state": "TX"
      },
      "confidence": "high"
    },
    {
      "claim_type": "location_county",
      "claim_value": {
        "county": "Ellis"
      },
      "confidence": "high"
    }
  ]
}
```

**Output**

* one or more claim_id values
* review_status should start as `unreviewed`
* next_action should suggest `link_claim`

**What success looks like**

* claims are created
* each has a claim_id
* each is attached to the evidence

---

### Step 3 — Check the Queues

**Endpoints**

```text
GET /queue/evidence
GET /queue/claims
```

**Purpose**
Understand what needs to happen next.

#### Evidence queue

Shows evidence items needing analyst attention.

Possible buckets:

* unclaimed
* claims_unlinked
* claims_pending_review
* review_complete

#### Claim queue

Shows claims needing:

* linking
* review
* acceptance
* or terminal handling

Possible buckets include:

* needs_link
* needs_review
* accepted
* rejected

**What to look for**

* recommended_action
* entity_label if already linked
* evidence title
* claim type
* queue bucket

**What success looks like**

* the evidence you created appears in the appropriate bucket
* the claims appear with the expected recommended_action

---

### Step 4 — Link Claims

**Endpoint**

```text
POST /claims/{claim_id}/link
```

**Purpose**
Assign a claim to the project or phase it belongs to.

**Preferred request shape**
Use aliases:

* project_id
* phase_id

Do not mix raw entity_type/entity_id unless you know you need to.

**Project-level example**

```json
{
  "project_id": "f66cad7e-ef4e-4b1c-b933-a5f7de1ac2d4"
}
```

**Phase-level example**

```json
{
  "phase_id": "PUT_PHASE_ID_HERE"
}
```

**When to link to project**
Use project for:

* project name
* developer
* state
* county
* project-level facts

**When to link to phase**
Use phase for:

* phase load
* phase timing
* phase-specific power path
* phase-specific disruption signals

**If unclear**
Do not force it.
Leave unlinked or return later.

**Output**

* claim_id
* entity_type
* entity_id
* entity_label
* review_status should become linked
* next_action should suggest `review_claim`

**What success looks like**

* claim is now associated with the correct entity
* entity_label is human-readable
* claim moves out of `needs_link`

---

### Step 5 — Review Claims

**Endpoint**

```text
POST /claims/{claim_id}/review
```

**Purpose**
Make an analyst judgment about the linked claim.

**Possible review_status values**

* accepted_candidate
* rejected
* ambiguous
* needs_more_review

**Example accepted candidate**

```json
{
  "review_status": "accepted_candidate",
  "reviewer": "test@local",
  "notes": "Clearly stated in source.",
  "is_contradictory": false
}
```

**Example ambiguous**

```json
{
  "review_status": "ambiguous",
  "reviewer": "test@local",
  "notes": "Project seems correct, but phase attribution is unclear.",
  "is_contradictory": false
}
```

**Example needs more review**

```json
{
  "review_status": "needs_more_review",
  "reviewer": "test@local",
  "notes": "Conflicts with another source or lacks clarity.",
  "is_contradictory": true
}
```

**Output**

* updated review_status
* reviewed_at
* reviewed_by
* review_notes
* next_action

**What success looks like**

* accepted_candidate claims return next_action `accept_claim`
* ambiguous claims remain unresolved honestly

---

### Step 6 — Accept Claims

**Endpoint**

```text
POST /claims/{claim_id}/accept
```

**Purpose**
Promote a reviewed claim into normalized system truth and create provenance.

**Important constraints**
A claim:

* must already be `accepted_candidate`
* must not be contradictory

**Example**

```json
{
  "accepted_by": "test@local",
  "notes": "Accepted from primary pilot source."
}
```

**Output**

* review_status should become accepted
* accepted_at
* accepted_by
* normalized_update
* field_provenance
* entity_label
* next_action

**What acceptance does**

* updates the normalized target field
* creates a provenance record
* does not delete previous claims

**Safe fields to accept first in a pilot**

* project_name_mention
* developer_named
* location_state
* location_county

**Accept later only if clearly stated**

* modeled_load_mw
* target_energization_date

**What success looks like**

* field update is returned
* field_provenance is created
* accepted_at and accepted_by are present

---

### Step 7 — Verify Evidence Detail

**Endpoint**

```text
GET /evidence/{evidence_id}
```

**Purpose**
Inspect the evidence record and everything tied to it.

**What to expect**

* evidence metadata
* linked_claims
* unlinked_claims
* provenance_links

**What success looks like**

* accepted claims appear under linked_claims
* provenance rows exist for accepted claims
* unlinked_claims is empty if you completed linking

---

### Step 8 — Verify Project Evidence View

**Endpoint**

```text
GET /projects/{project_id}/evidence
```

**Purpose**
Confirm the evidence is visible from the project side.

**What to expect**

* the evidence record listed under the project
* claim_ids
* accepted field_names
* related phase/event references if applicable

**What success looks like**

* the newly created evidence appears under the project
* accepted field names are visible
* the project now has an evidence-backed audit trail

---

## 8. Pilot Workflow Summary

For a minimal pilot, use this sequence:

```text
1. POST /evidence
2. POST /evidence/{id}/claims
3. GET /queue/evidence
4. GET /queue/claims
5. POST /claims/{id}/link
6. POST /claims/{id}/review
7. POST /claims/{id}/accept
8. GET /evidence/{id}
9. GET /projects/{id}/evidence
```

---

## 9. Working Rules

### Rule 1 — Do not skip the sequence

Always:

* create evidence first
* create claims second
* link before review
* review before accept
* verify after accept

---

### Rule 2 — Do not force certainty

If something is unclear:

* leave it unlinked
* mark it ambiguous
* mark it needs_more_review

Do not guess phase linkage.
Do not guess load basis.
Do not guess whether a value is primary vs optional expansion.

---

### Rule 3 — Accept conservatively

Accept only facts that are:

* directly stated
* clearly attributable
* high confidence
* non-contradictory

---

### Rule 4 — Preserve contradictions

Conflicting claims should remain in the system.
Do not delete old claims because a new source disagrees.

---

### Rule 5 — Provenance must exist

If a claim has been accepted, there must be a provenance record linking:

* field_name
* entity
* claim
* evidence

---

### Rule 6 — Do not confuse source with truth

Evidence is not truth.
Claims are not truth.
Only accepted claims become normalized truth.

---

## 10. Best Practices

* Start with one source at a time
* Extract only a few high-value claims
* Link carefully before reviewing
* Accept only what you trust
* Verify every acceptance through evidence detail
* Keep notes concise and meaningful
* Use accepted_candidate only when you are ready to consider acceptance

---

## 11. What Not To Do

Do not:

* bulk ingest many sources before the workflow is stable
* accept uncertain values
* review unlinked claims as accepted_candidate
* confuse project-level and phase-level claims
* overwrite conflicting data manually
* use the UI as the primary ingestion surface yet
* assume every source should produce accepted claims

---

## 12. Common Errors and Fixes

### Error: Claim must be linked before it can be marked accepted_candidate

**Cause**
You tried to review a claim as accepted_candidate before linking it.

**Fix**
Run:

```text
POST /claims/{claim_id}/link
```

first.

---

### Error: Only accepted_candidate claims can be accepted

**Cause**
You tried to accept a claim before review.

**Fix**
Run:

```text
POST /claims/{claim_id}/review
```

with:

* accepted_candidate
* rejected
* ambiguous
* needs_more_review

Then retry accept only if it is accepted_candidate.

---

### Error: Contradictory claims cannot be accepted

**Cause**
The claim is marked contradictory.

**Fix**
Leave it unresolved or mark needs_more_review. Do not accept.

---

### Error: Project not found

**Cause**
Wrong ID type was passed to a project-scoped endpoint.

**Fix**
Use the correct ID:

* project_id for project endpoints
* evidence_id for evidence endpoints
* claim_id for claim endpoints

---

### Error: Confusion about where to put project_id

**Cause**
Trying to attach project_id during evidence creation.

**Fix**
Do not put project_id in POST /evidence.
Evidence is created first, then claims are linked to projects/phases.

---

### Error: Evidence created but not visible under project

**Cause**
Claims may not be linked or accepted yet.

**Fix**
Check:

* claims exist
* claims are linked to the project
* accepted claims have provenance

---

## 13. ID Reference Guide

| ID Type     | Meaning        | Used In                                     |
| ----------- | -------------- | ------------------------------------------- |
| evidence_id | source record  | evidence endpoints                          |
| claim_id    | extracted fact | claim endpoints                             |
| project_id  | project entity | project endpoints and project linking       |
| phase_id    | phase entity   | phase linking and phase-specific operations |

### Quick rule

* Evidence endpoints use evidence_id
* Claim endpoints use claim_id
* Project endpoints use project_id
* Phase linking uses phase_id

---

## 14. Claim Types for the Initial Pilot

Use only a small set for the first real pilots:

* project_name_mention
* developer_named
* location_state
* location_county
* modeled_load_mw
* target_energization_date

Optional only if very clear:

* utility_named
* phase_name_mention
* latest_update_date
* announcement_date

Keep the pilot small and clean.

---

## 15. Recommended Source Types for Early Pilots

Best first source types:

* official_filing
* utility_statement
* developer_statement

Use if needed:

* county_record
* regulatory_record

Avoid for first pilots unless no better source exists:

* press
* other

---

## 16. Definition of Success

A successful ingestion means:

* the source exists as evidence
* claims were extracted from it
* claims were linked to the right entity
* claims were reviewed
* at least one claim was accepted
* a provenance record was created
* the result is visible in the project evidence view

Success does **not** require:

* all claims to be accepted
* all uncertainty to be resolved
* event creation
* automation

---

## 17. Current Limitations

Current limitations include:

* ingestion is API-only
* there is no dedicated ingestion UI yet
* claim typing is still a pilot set
* workflow is manual
* source extraction is manual
* real pilot scale is still small

These limitations are expected at this stage.

---

## 18. Future Improvements

Expected future improvements:

* ingestion UI / evidence workbench
* better queue views in the frontend
* clearer project/phase selection tools
* assisted extraction
* claim templates by source type
* batch workflows
* automated enrichment after the manual loop is stable

---

## 19. Final Principle

Every accepted fact in the system should satisfy this standard:

> It is traceable to a real source, through an explicit claim, linked to a specific entity, reviewed by a human, and recorded with provenance.

That is the operating standard for this system.

```
```
