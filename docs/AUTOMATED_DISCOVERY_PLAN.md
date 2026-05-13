# Automated Discovery Plan

## Goal

Build an automated discovery system for U.S. data center projects that are discoverable through public evidence. The system should make it easier to find, triage, and eventually ingest public-source-backed project candidates from regulatory dockets, utility filings, local planning records, economic development announcements, company/developer sources, data center news, and grid context sources.

## Non-goal

This is not a complete census of all U.S. data center projects. Hidden, private, rumored, or otherwise non-public projects are out of scope until a public source exists.

## Core Rule

No public source, no project record.

A project can enter the dataset only when it has a source URL or source document that supports the project candidate. Automated discovery may create candidates for analyst review, but publication requires traceable public evidence.

## Evidence vs Context

Project evidence directly supports a project record or project claim. Examples include a developer announcement naming a campus, a county planning agenda describing a data center application, a utility filing identifying a large-load customer, or an economic development release naming a project.

Context data helps interpret risk, geography, grid exposure, utility territory, or regional constraints, but does not by itself create a project record. Examples include EIA/EIA-861 utility data, HIFLD utility territories, interconnection queues, regional grid reports, or transmission context. Context sources can enrich or validate project records only after project evidence exists.

## Confidence Categories

- `confirmed_discovered`: Public source directly names or clearly identifies a data center project and at least one core project attribute such as developer, location, load, phase, or schedule.
- `probable_discovered`: Public source strongly indicates a data center project but one or more core identity fields remain unresolved or indirect.
- `candidate_discovered`: Public source suggests a possible data center project and requires analyst review before any project record is published.
- `context_only`: Source provides grid, utility, geographic, or market context but does not establish a data center project.
- `quarantined`: Source or extracted item is unusable for publication because it is unsupported, contradictory, too vague, inaccessible, non-public, duplicate, or fails schema/quality checks.

## Pipeline Stages

1. Source registry
2. Source discovery
3. Document fetch/cache
4. Text/PDF extraction
5. Project candidate extraction
6. Evidence claim extraction
7. Entity resolution/deduplication
8. Coordinate/utility/ISO enrichment
9. Confidence scoring
10. Quarantine
11. Publish dataset/report

## Source Registry

The source registry describes public source families and seed patterns. Registry entries are not evidence by themselves. They define where discovery should look, how discovery would be performed, and whether the source is project evidence or context-only.

Initial registry categories:

- `state_regulatory_dockets`
- `utility_large_load_filings`
- `county_city_planning`
- `economic_development_announcements`
- `company_press_releases`
- `developer_websites`
- `data_center_news`
- `grid_context`

## First Adapter: Virginia SCC

Virginia SCC docket discovery is the first implemented adapter. In dry-run mode it plans searches for the registry terms `data center`, `large load`, `electric service agreement`, and `transmission interconnection` without fetching public pages.

In non-dry-run mode the adapter only attempts to discover public source records. It does not create project records, extract project candidates, resolve entities, or infer facts. If the SCC public search or docket pages cannot be parsed reliably, the adapter returns warnings and no discovered source records rather than fabricating results.

Extraction, claim parsing, entity resolution, coordinate enrichment, utility/ISO enrichment, confidence scoring, and publication remain later pipeline stages. The public discoverability rule remains unchanged: no source, no project.

## Public Fetch Policy

Discovery fetches use SSL certificate verification by default. SSL failures are reported as structured diagnostics and must not crash discovery runs or silently hide the problem.

An explicit `--allow-insecure-fetch` flag exists for local debugging only. When used, discovery output must warn loudly and mark fetch results with `insecure_fetch=true`. This flag must not be used for published datasets.

Fetched content and metadata are runtime data. If persisted for debugging or review, they belong under ignored paths such as `data/source_fetches/` or `data/discovery_runs/`, not in committed source control.

## Generated Data Policy

Generated discovery output is runtime data and is not committed:

- `data/generated/`
- `data/cache/`
- `data/source_fetches/`
- `data/discovery_runs/`
- backend runtime discovery outputs
- geocoding caches

Curated demo data under `data/demo/` is committed because it is manually reviewed and presentation reproducible. Automated discovered data must include a `source_url` or source document before it can become a project candidate, and it must pass analyst review before publication.
