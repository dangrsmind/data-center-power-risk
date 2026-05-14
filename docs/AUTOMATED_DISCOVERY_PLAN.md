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

In non-dry-run mode the adapter fetches the SCC public search shell through the shared public fetch client and extracts the public SearchStax Studio configuration embedded in the page. The static SCC search HTML is client-rendered and does not contain result records; it contains the SearchStax script URLs, tab facet IDs, and connector configuration used by the browser.

Current API discovery status: a public SearchStax `emselect` endpoint is exposed by the SCC search page at `https://searchcloud-2-us-east-1.searchstax.com/29847/vcascc-1781/emselect`. The browser calls it with `Authorization: Token <select_auth_token>`, `q`, `rows`, `start`, `spellcheck.correct`, `language`, optional `fq` facet filters, and SCC's additional `hl.fragsize=200` argument. Result fields observed include `url`, `id`, `dctitle_t`, `content`, `type_s`, `sectionType_s`, `CaseNumberPrefix_t`, `CaseNumberCaseNumber_t`, `DocumentType_s`, `LongName_txt_en`, `MetaDescription_txt_en`, and highlighting snippets. SCC search tabs map to facets for all results, site pages (`type_s:web page`), news (`sectionType_s:news`), cases (`sectionType_s:case`), and PDFs/file types through `type_s`.

Parsed SearchStax results are emitted only as discovered source records with source URLs, titles when present, publisher/geography, search term, snippet, case number/document type when available, SearchStax discovery method, and analyst-review confidence. It does not create project records, extract project candidates, resolve entities, or infer facts. If the SearchStax config is missing, requires unsupported dynamic authentication, or cannot be queried without browser execution, the adapter returns `scc_search_requires_client_side_execution` and no discovered source records rather than fabricating results.

Current limitations: the SearchStax token is public because SCC embeds it in the client page, but it is still an implementation detail of SCC's website and may rotate or change. The adapter does not use browser automation. TODO: add browser-rendered discovery or request official SCC/API access if the public connector begins requiring dynamic tokens or browser-only execution.

Extraction, claim parsing, entity resolution, coordinate enrichment, utility/ISO enrichment, confidence scoring, and publication remain later pipeline stages. The public discoverability rule remains unchanged: no source, no project.

## Discovered Source Ingestion

Discovery run output remains runtime data and is ignored under `data/discovery_runs/`. When a run finds source records, `backend/scripts/ingest_public_discovered_sources.py --input data/discovery_runs/<timestamp>/discovered_sources.json` can validate those records and upsert them into the database `discovered_sources` table by `source_url`.

Ingested discovered sources are source/evidence candidates only. Ingestion stores URLs, titles, publisher/geography, discovery method, search term, snippet, case number/document type, registry/adapter context when present, raw metadata, and review status. It does not create projects, claims, project links, or promoted evidence. Re-running the ingest is idempotent: existing URLs are skipped by default or updated with `--allow-existing`.

The next stage after discovered-source ingestion is document fetch/text extraction and analyst-reviewed project/candidate extraction. A discovered source must still support a project-specific public claim before any project record is created.

## Extracted Claims From Discovered Sources

Ingested discovered sources can now be followed by conservative extracted claim generation with `backend/scripts/extract_discovered_source_claims.py`. The extractor reads `discovered_sources`, uses only already-ingested fields such as title, URL, publisher, geography, search term, snippet, case number, document type, and raw metadata, and writes reviewable rows to `discovered_source_claims`.

These extracted claims are not project records, not final evidence claims, and not promoted source records. They are review candidates with `extracted`, `rejected`, or `promoted` status. The initial rule-based extractor is intentionally narrow: it can emit explicit case numbers, clear MW mentions, SCC/Virginia state context, document type, and general relevance terms such as `data center`, `large load`, `electric service agreement`, or `transmission interconnection`. It should not infer hidden facts, vague locations, developers, or project names unless a clear labeled phrase exists in the source text.

## Project Candidate Generation

Extracted discovered-source claims can now be grouped into reviewable rows in the separate `project_candidates` table with `backend/scripts/generate_project_candidates.py`. Candidate generation uses explicit extracted claim types only: `possible_project_name`, `developer`, `state`, `county`, `city`, `utility`, and `load_mw` populate candidate fields; `general_relevance`, case numbers, source IDs, and excerpts are supporting context.

Project candidates are not final `projects` rows, are not map markers, and are not prediction inputs. If no explicit `possible_project_name` claim exists, the generator uses a cautious unresolved label such as `Unresolved Virginia SCC candidate <source id>` rather than inferring a project name from vague source titles. It does not infer county/city from state, invent developers, invent load, or promote anything automatically.

Promotion from project candidates to final projects, accepted evidence claims, map display, or prediction scoring remains a later reviewed workflow. The core rule remains unchanged: no public source, no project record.

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
