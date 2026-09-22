"""Offline primary-source alignment hints; never fetched content verification."""
import re
from functools import lru_cache
from urllib.parse import unquote, urlsplit

from app.services.csv_dataset_importer import STATE_BY_NAME

CATEGORIES = ('aligned', 'weakly_aligned', 'geography_mismatch', 'facility_or_operator_mismatch',
              'broad_transaction_or_platform_article', 'cancelled_or_rejected_project',
              'insufficient_source_row_alignment', 'unknown')
STOP = set('data center centers centre project campus facility site power digital infrastructure redevelopment technology park company corporation corp inc llc ltd the of and proposed new'.split())
TERMINAL = r'\b(cancelled|canceled|scrapped|withdrawn|withdraws|abandoned)\b'
REJECTED = r'\b(rejected|denied|voted down|(?:fail|failed|fails) to back)\b'
TRANSACTION = r'\b(platform|acquisition|acqui(?:re|res|red)|portfolio|carrier hotels?|sale leaseback|market transaction)\b'
BUILD = r'\b(proposed|proposes|proposal|plans|planned|planning|build|building|construction|expansion|expands|expanding|redevelopment)\b'


def words(value):
    return ' '.join(re.findall(r'[a-z0-9]+', str(value or '').lower()))


def contains(text, phrase):
    return bool(phrase) and (' ' + phrase + ' ') in (' ' + text + ' ')


def identity(value):
    return {t for t in words(value).split() if t not in STOP and len(t) >= 2}


def primary_source_text(url, normalized, raw_row, urls):
    """Dedicated primary-title fields are bound; generic titles need one URL or
    an explicit URL binding. Never use concatenated secondary-source text."""
    raw = {re.sub(r'[^a-z0-9]+', '_', str(k).lower()).strip('_'): v
           for k, v in (raw_row.items() if isinstance(raw_row, dict) else [])}
    pieces = []
    try:
        pieces.append(words(unquote(urlsplit(url or '').path)))
    except ValueError:
        pass
    for record in (normalized, raw):
        value = record.get('primary_source_title')
        if isinstance(value, str):
            pieces.append(words(value))
        bound = record.get('source_url') == url or record.get('primary_source_url') == url
        if bound or len(urls) == 1:
            for key in ('source_title', 'article_title'):
                if isinstance(record.get(key), str):
                    pieces.append(words(record[key]))
    return ' '.join(pieces), raw


@lru_cache(maxsize=16384)
def city_location_pattern(city):
    return re.compile(r'\b(?:in|near|at) ' + re.escape(city) + r'\b')


def classify_source_row_alignment(normalized, urls, raw_row=None, known_cities=()):
    url = urls[0] if urls else None
    text, raw = primary_source_text(url, normalized, raw_row, urls)

    def result(category, allows, *reasons):
        return {'source_row_alignment': category,
                'source_row_alignment_allows_candidate_creation': allows,
                'source_row_alignment_reasons': list(reasons)}

    row_status = words(normalized.get('lifecycle_state'))
    if re.search(TERMINAL + '|' + REJECTED, text) or re.search(TERMINAL + '|' + REJECTED, row_status):
        return result('cancelled_or_rejected_project', False,
                      'Primary source or row status indicates cancellation, withdrawal, rejection or lack of official support; not an active build.')
    if not url or not text.strip():
        return result('unknown', False, 'No usable primary-source path/title for alignment.')
    state = str(normalized.get('state') or '').upper()
    state = STATE_BY_NAME.get(words(state), state)
    source_states = {code for name, code in STATE_BY_NAME.items() if contains(text, name)}
    # Avoid nested names: West Virginia is not a Virginia match.
    if contains(text, 'west virginia'):
        source_states.discard('VA')
    if contains(text, 'californian'):
        source_states.add('CA')
    # Abbreviations only in an explicit location construction, not ordinary
    # words such as "in", "or", "me", or corporate "co".
    for code in set(STATE_BY_NAME.values()):
        city = words(normalized.get('city'))
        if re.search(r'\b(?:in|near|at) ' + code.lower() + r'\b', text) or (city and contains(text, city + ' ' + code.lower())):
            source_states.add(code)
    city = words(normalized.get('city'))
    city_match = contains(text, city)
    state_match = bool(state and state in source_states)
    source_cities = {words(c) for c in known_cities if words(c) and
                     city_location_pattern(words(c)).search(text)}
    other_cities = source_cities - {city}
    # Matching row state or city explicitly in source provides the requested
    # conservative exception (e.g. Brisbane / near San Francisco, California).
    if state and source_states - {state} and not (state_match or city_match):
        return result('geography_mismatch', False,
                      f'Row state {state}; primary source explicitly names state(s) {", ".join(sorted(source_states))}.')
    if city and other_cities and not (city_match or state_match):
        return result('geography_mismatch', False,
                      f'Row city {normalized.get("city")}; primary source locates the project in/near {", ".join(sorted(other_cities))}.')
    tokens = identity(normalized.get('name')) | identity(normalized.get('operator')) | identity(normalized.get('developer'))
    matching = sorted(tokens & set(text.split()))
    # These fields, when present, explicitly name the primary source's subject.
    for key, row_key in (('primary_source_facility_name', 'name'), ('primary_source_operator', 'operator')):
        subject = normalized.get(key) or raw.get(key)
        row_subject = normalized.get(row_key)
        if subject and row_subject and identity(subject) and identity(row_subject) and not identity(subject) & identity(row_subject):
            return result('facility_or_operator_mismatch', False, f'{key} does not match the row {row_key}.')
    source_build = bool(re.search(BUILD, text))
    conversion = bool(re.search(r'\b(?:for|into|to develop)\b.*\bdata center\b', text))
    if re.search(TRANSACTION, text):
        specific = (city_match or state_match) and (source_build or (conversion and bool(matching)))
        if not specific:
            return result('broad_transaction_or_platform_article', False,
                          'Primary source describes a platform/acquisition/portfolio transaction without a specific build or conversion supported at the row location.')
    if matching and (source_build or conversion):
        return result('aligned', True, 'Distinctive row facility/operator token(s) match primary source: ' + ', '.join(matching) + '; source describes a build/proposal/conversion.')
    if city_match and source_build:
        return result('aligned', True, 'Primary source names the row city and a specific build/expansion/proposal.')
    if state_match and source_build:
        return result('weakly_aligned', True, 'Primary source names the row state and a build/proposal; exact facility/city identity still requires analyst review.')
    return result('insufficient_source_row_alignment', False,
                  'Primary source lacks a matching distinctive facility/operator or location together with a specific build signal.')


def rejected_taxonomy(normalized, urls, raw_row=None):
    text, _ = primary_source_text(urls[0] if urls else None, normalized, raw_row, urls)
    terminal = bool(re.search(TERMINAL, text + ' ' + words(normalized.get('lifecycle_state'))))
    return {'lifecycle_stage': 'cancelled' if terminal else 'unknown',
            'candidate_purpose': 'supporting_context' if terminal else 'permitting_or_policy_signal'}
