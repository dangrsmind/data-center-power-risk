"""Offline preview taxonomy. Topic tags are mentions, never verified constraints."""
import re
from urllib.parse import unquote, urlsplit

ENTITY_TYPES = ('data_center_project', 'data_center_facility', 'data_center_campus',
                'power_generation_asset', 'grid_interconnection_asset', 'cooling_water_asset',
                'equipment_supply_chain_signal', 'policy_permitting_case', 'supporting_context', 'unknown')
LIFECYCLE_STAGES = ('existing_operational', 'under_construction', 'proposed', 'planned_expansion',
                    'speculative_or_unverified', 'cancelled', 'retired', 'unknown')
CANDIDATE_PURPOSES = ('build_review', 'facility_baseline', 'infrastructure_context', 'supply_chain_signal',
                      'permitting_or_policy_signal', 'supporting_context', 'unknown')
DOMAIN_PATTERNS = {
    'grid_capacity': r'\b(grid|interconnection|substations?|transmission|transformers?)\b',
    'onsite_power': r'\b(on ?site power|on ?site generation|behind the meter|fuel cells?|power plants?|gas turbines?)\b',
    'gas_turbine_supply': r'\b(gas turbines?|combustion turbines?|turbine supply|turbine shortages?)\b',
    'transformer_supply': r'\btransformers?\b',
    'backup_generation': r'\b(generators?|backup generation|standby power)\b',
    'fuel_supply': r'\b(fuel supply|gas supply|natural gas|fuel cells?|fuel pipelines?|diesel supply)\b',
    'air_emissions': r'\b(emissions?|air permits?|air quality|air pollution)\b',
    'water_cooling': r'\b(water|cooling|cooling towers?|chillers?)\b',
    'land_use_zoning': r'\b(zoning|rezoning|land use|planning permission)\b',
    'community_opposition': r'\b(opposition|community pushback|protests?|petitions?|opponents?)\b',
    'legal_regulatory': r'\b(permits?|permitting|regulatory|regulation|litigation|lawsuits?|policy|solicitation|rfp)\b',
    'cost_financing': r'\b(costs?|financing|funding|capital expenditure|capex|investment)\b',
    'schedule_delay': r'\b(delays?|delayed|shortages?|lead times?|schedule slippage)\b',
}
TEXT_FIELDS = ('name', 'notes', 'lifecycle_state', 'power_source', 'cooling', 'cooling_type')
RAW_TEXT_FIELDS = {'notes', 'other_info', 'purpose', 'power_source', 'dedicated_power_plant',
                   'cooling_source', 'cooling_type', 'advocacy_information', 'resistance_status'}


def words(value):
    return re.sub(r'[-_/]+', ' ', value.lower()) if isinstance(value, str) else ''


def has(pattern, text):
    return bool(re.search(pattern, text, re.I))


def active(value):
    return isinstance(value, (str, int, float)) and str(value).strip().lower() not in {
        '', '0', '0.0', 'no', 'none', 'unknown', 'n/a', 'na', 'null', 'false'}


def lifecycle(text):
    # Negative/terminal states take precedence; mixed expansion+operating rows
    # describe planned expansion, not a newly invented operational project.
    if has(r'\b(not|no longer)\s+(operating|operational|under construction|planned|proposed)\b', text):
        return 'unknown'
    if has(r'\b(cancelled|canceled|abandoned)\b', text):
        return 'cancelled'
    if has(r'\b(retired|decommissioned|closed permanently)\b', text):
        return 'retired'
    if has(r'\b(speculative|unverified|rumou?red)\b', text):
        return 'speculative_or_unverified'
    if has(r'\b(under construction|construction underway|being built)\b', text):
        return 'under_construction'
    if has(r'\b(expansion|expand|expanding)\b', text) and has(r'\b(planned|proposed|plans|planning)\b', text):
        return 'planned_expansion'
    if has(r'\b(proposed|proposal|planned|plans to build|planning)\b', text):
        return 'proposed'
    if has(r'\b(operating|operational|in operation)\b', text):
        return 'existing_operational'
    return 'unknown'


def classify_entity_taxonomy(normalized, quality, urls=(), raw_row=None):
    raw = {re.sub(r'[^a-z0-9]+', '_', str(k).lower()).strip('_'): v
           for k, v in (raw_row.items() if isinstance(raw_row, dict) else [])}
    # URL paths contribute topical context, never host/query guesses or fetches.
    paths = []
    for url in urls:
        try:
            paths.append(words(unquote(urlsplit(url).path)))
        except (ValueError, TypeError):
            pass
    primary = paths[0] if paths else ''
    name = words(normalized.get('name'))
    row_text = ' '.join(words(normalized.get(k)) for k in TEXT_FIELDS)
    topics = ' '.join([row_text, *paths, *(words(raw.get(k)) for k in sorted(RAW_TEXT_FIELDS))])
    domains = {key for key, pattern in DOMAIN_PATTERNS.items() if has(pattern, topics)}
    if active(normalized.get('cooling')) or active(normalized.get('cooling_type')) or any(active(raw.get(k)) for k in ('cooling_source', 'cooling_type')):
        domains.add('water_cooling')
    if isinstance(normalized.get('water_use_mgd'), (int, float)) and normalized['water_use_mgd'] > 0:
        domains.add('water_cooling')
    try:
        if float(raw.get('number_of_generators', 0)) > 0:
            domains.add('backup_generation')
    except (ValueError, TypeError):
        pass
    if str(raw.get('community_pushback', '')).lower() in {'yes', 'true', '1'}:
        domains.add('community_opposition')

    report_text = ' '.join((row_text, primary))
    report_supply = has(r'\b(turbines?|generators?|fuel cells?|transformers?|chillers?|cooling towers?)\b', report_text) and has(r'\b(supply|supply chain|shortages?|manufacturing|manufacturer|lead times?)\b', report_text)
    source = quality['source_quality']
    ctype = quality['candidate_type']
    identity = ' '.join((name, primary))
    equipment = has(r'\b(turbines?|generators?|fuel cells?|transformers?|chillers?|cooling towers?)\b', identity)
    supply = equipment and has(r'\b(supply|supply chain|shortages?|manufacturing|manufacturer|factory|production|lead times?)\b', ' '.join((identity, row_text)))
    data_center_named = has(r'\b(data cent(?:er|re)|datacent(?:er|re)|campus|colocation)\b', name)
    row_stage = lifecycle(words(normalized.get('lifecycle_state')))
    entity, purpose = 'unknown', 'unknown'
    if source == 'social_media_or_group':
        entity, purpose = 'supporting_context', 'supporting_context'
    elif ctype == 'programmatic_solicitation_or_policy':
        if has(r'\b(solicitation|request for proposals|rfp|policy|accepting proposals|military bases|permitting|regulatory case)\b', ' '.join((identity, row_text))):
            entity, purpose = 'policy_permitting_case', 'permitting_or_policy_signal'
            domains.add('legal_regulatory')
        else:
            entity, purpose = ('equipment_supply_chain_signal', 'supply_chain_signal') if report_supply else ('supporting_context', 'supporting_context')
    elif source in {'broad_report_or_index', 'advocacy_or_watchdog_report'}:
        entity, purpose = ('equipment_supply_chain_signal', 'supply_chain_signal') if report_supply else ('supporting_context', 'supporting_context')
    elif supply:
        entity, purpose = 'equipment_supply_chain_signal', 'supply_chain_signal'
    elif not data_center_named and has(r'\b(power plants?|generation assets?|fuel cells?|on ?site power|on ?site generation)\b', name):
        entity, purpose = 'power_generation_asset', 'infrastructure_context'
    elif not data_center_named and has(r'\b(substations?|interconnection|transmission)\b', name):
        entity, purpose = 'grid_interconnection_asset', 'infrastructure_context'
    elif not data_center_named and has(r'\b(cooling towers?|chillers?|water treatment|water supply)\b', name):
        entity, purpose = 'cooling_water_asset', 'infrastructure_context'
    elif not data_center_named and has(r'\b(permit|permitting|zoning case|regulatory case|policy)\b', identity):
        entity, purpose = 'policy_permitting_case', 'permitting_or_policy_signal'
    elif data_center_named or ctype in {'operating_facility_or_colocation_page', 'project_specific_build_or_expansion'}:
        if has(r'\bcampus\b', name):
            entity = 'data_center_campus'
        elif ctype == 'operating_facility_or_colocation_page' or row_stage == 'existing_operational':
            entity = 'data_center_facility'
        else:
            entity = 'data_center_project'
        if ctype == 'project_specific_build_or_expansion':
            purpose = 'build_review'
        elif ctype == 'operating_facility_or_colocation_page' or row_stage == 'existing_operational':
            purpose = 'facility_baseline'
        else:
            purpose = 'supporting_context'
    elif source != 'unknown':
        entity, purpose = 'supporting_context', 'supporting_context'

    stage = 'unknown'
    if entity not in {'supporting_context', 'equipment_supply_chain_signal', 'policy_permitting_case', 'unknown'}:
        stage = row_stage
        if not words(normalized.get('lifecycle_state')).strip():
            stage = lifecycle(' '.join((name, primary)))
    return {'entity_type': entity, 'lifecycle_stage': stage, 'candidate_purpose': purpose,
            'constraint_domains': sorted(domains)}


def empty_taxonomy_summary():
    return {key: {} for key in ('entity_type_counts', 'lifecycle_stage_counts', 'candidate_purpose_counts', 'constraint_domain_counts')}


def count_taxonomy(summary, taxonomy):
    for field in ('entity_type', 'lifecycle_stage', 'candidate_purpose'):
        counts = summary[field + '_counts']
        value = taxonomy[field]
        counts[value] = counts.get(value, 0) + 1
    for domain in taxonomy['constraint_domains']:
        counts = summary['constraint_domain_counts']
        counts[domain] = counts.get(domain, 0) + 1
