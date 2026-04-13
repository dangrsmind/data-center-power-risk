Build the v1 internal analyst console for a forecasting platform that tracks power-linked impairment risk in large U.S. data-center projects.

Assume the backend API exists or can be mocked first.

Primary users:
- analyst
- reviewer

Build these views:
1. Project list
   - filters: MW bucket, region/RTO, utility, lifecycle state, risk tier, review status
   - sortable columns: current score, deadline probability, data quality score, latest update date
2. Project detail page
   - canonical project info
   - phase breakdown
   - normalized load fields
   - current score and cumulative probability
   - top drivers
   - evidence timeline
   - audit trail
3. Adjudication queue
   - candidate positives
   - ambiguous cases
   - contradiction cases
   - phase-splitting reviews
4. Evidence review UI
   - source metadata
   - extracted claims
   - contradiction markers
   - reviewer decision controls
5. Scenario panel
   - toggle assumptions like non-firm service available, transformer lead times improve, transmission delayed
   - show score delta and driver changes
6. Data quality panel
   - production-readiness score
   - missing-field checklist
   - observability indicators
7. Score history view
   - historical score updates by quarter
   - explanation changes over time

UI requirements:
- internal-tool style, not marketing site
- table-first workflow with detail drawers or side panels
- explicit uncertainty and evidence strength
- easy reviewer actions
- can start with mocked JSON and later connect to real API
- simple auth is fine for v1

Expected backend payloads:
- projects list
- project detail
- phase detail
- evidence records
- adjudication queue items
- current score object
- historical score series
- scenario response object
- data quality object

Deliver:
- working Replit app
- mock data layer
- clear API adapter layer
- easy switch from mocks to real backend
- local and hosted run instructions