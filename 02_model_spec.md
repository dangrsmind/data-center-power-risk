Implement the forecasting core as a discrete-time hazard model over `project_phase_quarter` rows.

Specification:

* One row = one project phase in one calendar quarter.
* Include rows from first announcement quarter until first qualifying event or censoring date.
* Label `y = 1` only in the first quarter where a qualifying public power-linked delay, downsizing, or cancellation occurs.
* Label `y = 0` in all prior quarters.
* Exclude all rows after the first qualifying event.
* Use lagged features from quarter `t-1` to predict the event in quarter `t`.

Model:

* Fit logistic regression for quarterly hazard:
  `logit(h_t) = age_quarter_effect + calendar_quarter_effect + beta * features_(t-1)`
* `h_t` means: probability of first qualifying event in quarter `t`, conditional on no prior qualifying event.

Required features in v1:

* `log_primary_mw`
* `project_age_quarters`
* `announce_year`
* `region_or_rto`
* `utility_identified`
* `power_path_identified`
* `onsite_generation_planned`
* `new_transmission_required`
* `new_substation_required`
* `new_generation_required`
* `novel_service_or_nonfirm_flag`
* `electrical_dependency_complexity_score`
* `official_update_count_trailing_2q`
* `credible_update_count_trailing_2q`
* `electrical_constraint_term_count_trailing_2q`
* `observability_score`

Outputs:

* quarterly hazard for each active project-phase-quarter
* cumulative probability by deadline:
  `P(event by T) = 1 - product_over_quarters(1 - h_t)`
* top contributing features for the current score
* stored score history by project phase and quarter

Data rules:

* unit of analysis is always `project_phase_quarter`
* use `modeled_primary_load_mw`, not headline MW
* keep `optional_expansion_mw` separate and never merge it into primary load unless explicitly firm
* all qualifying positive labels must remain human-reviewed
* do not use random train/test split; use rolling temporal backtests only
