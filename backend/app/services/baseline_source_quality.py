"""Conservative offline hints, not source verification or final admission rules."""
import re
from urllib.parse import unquote, urlsplit

from app.services.baseline_dataset_profiles import public_url

SOCIAL = {'facebook.com', 'fb.com', 'reddit.com', 'x.com', 'twitter.com', 'instagram.com',
          'linkedin.com', 'nextdoor.com', 'discord.com', 'discord.gg', 't.me', 'youtube.com'}
NEWS = {'datacenterdynamics.com', 'datacenterknowledge.com', 'reuters.com', 'apnews.com',
        'tucson.com', 'azpm.org', 'fox10phoenix.com', 'lakepowellchronicle.com'}
OFFICIAL = {'expedient.com', 'tract.com', 'equinix.com', 'digitalrealty.com', 'qtsdatacenters.com',
            'vantage-dc.com', 'aligneddc.com', 'cyrusone.com'}
ADVOCACY = {'datacenterwatch.org', 'change.org', 'fractracker.org'}
BROAD = {'', 'report', 'reports', 'index', 'news', 'en/news', 'blog', 'data-centers', 'locations', 'portfolio', 'research'}
BUILD = re.compile(r'\b(proposed?|proposes|proposal|planned|plans|planning|build|construction|expansion|expand|expands|expanding|redevelopment|rezoning|approved|permitted|breaks ground|groundbreaking)\b', re.I)
PROGRAM = re.compile(r'\b(solicitation|request for proposals|rfp|policy|accepting proposals|military bases|market outlook|industry forecast)\b', re.I)
NEGATED = re.compile(r'\b(no|not|without)\s+(?:new\s+)?(?:build|building|expansion|construction|proposal|plans)\b', re.I)


def domain_in(host, domains):
    return any(host == domain or host.endswith('.' + domain) for domain in domains)


def classify_source_and_candidate(url, normalized):
    """Use only the selected primary URL and explicit normalized row fields.

    A secondary URL does not silently replace a weak primary source. Unknown
    domains remain blocked until a reviewed classifier change recognizes them.
    """
    parsed = urlsplit(url) if url and public_url(url) else None
    host = (parsed.hostname or '').lower() if parsed else ''
    path = unquote(parsed.path).strip('/').lower() if parsed else ''
    words = re.sub(r'[-_/]+', ' ', path)
    broad = path in BROAD or bool(re.search(r'(^|/)(reports?|index)(\.[a-z]+)?$', path))
    quality = 'unknown'
    if parsed:
        if domain_in(host, SOCIAL) or re.search(r'(^|/)(forums?|groups?)(/|$)', path):
            quality = 'social_media_or_group'
        elif broad:
            quality = 'broad_report_or_index'
        elif domain_in(host, ADVOCACY):
            quality = 'advocacy_or_watchdog_report'
        elif host.endswith('.gov') or host.endswith('.gov.uk'):
            quality = 'government_or_regulatory'
        elif domain_in(host, OFFICIAL):
            quality = 'official_project_or_operator'
        elif domain_in(host, NEWS) and len(path.split('/')) >= 2:
            quality = 'credible_news_article'
    source_allows = quality in {'official_project_or_operator', 'credible_news_article', 'government_or_regulatory'}
    # Do not mine evidence_text: it can contain unrelated secondary URL slugs.
    row_text = ' '.join(str(normalized.get(k) or '') for k in ('name', 'lifecycle_state', 'notes'))
    activity_text = ' '.join(str(normalized.get(k) or '') for k in ('lifecycle_state', 'notes'))
    named_project_signal = re.search(r'\b(proposed|expansion|redevelopment)\b', str(normalized.get('name') or ''), re.I)
    explicit_build = bool(BUILD.search(activity_text) or named_project_signal) and not NEGATED.search(row_text)
    url_build = bool(BUILD.search(words)) and not NEGATED.search(words)
    candidate_type = 'ambiguous'
    if PROGRAM.search(words) or PROGRAM.search(row_text):
        candidate_type = 'programmatic_solicitation_or_policy'
    elif broad and parsed:
        candidate_type = 'broad_market_or_report_reference'
    elif explicit_build or url_build:
        candidate_type = 'project_specific_build_or_expansion'
    elif quality == 'official_project_or_operator' and (re.search(r'\b(operating|operational|colocation)\b', row_text, re.I) or re.search(r'(^|/)(data-centers|locations|facilities|colocation)(/|$)', path)):
        candidate_type = 'operating_facility_or_colocation_page'
    type_allows = candidate_type == 'project_specific_build_or_expansion'
    if not source_allows:
        reason = {
            'social_media_or_group': 'Blocked: social-media group/forum URL is insufficient for baseline candidate creation.',
            'broad_report_or_index': 'Blocked: broad report/index URL is not project-specific.',
            'advocacy_or_watchdog_report': 'Blocked: advocacy/watchdog report is supporting context, not a direct creation source.',
        }.get(quality, 'Blocked: missing or unrecognized primary public source URL; source quality is unknown.')
    elif not type_allows:
        reason = {
            'operating_facility_or_colocation_page': 'Blocked: operating facility page does not establish a build/expansion candidate.',
            'programmatic_solicitation_or_policy': 'Blocked: programmatic solicitation/policy does not establish a specific build or expansion.',
        }.get(candidate_type, 'Blocked: no explicit build/expansion/proposal signal in the primary URL or row fields.')
    else:
        reason = f'Eligible: {quality} with explicit build/expansion/proposal signal; analyst source review still required.'
    return {'source_quality': quality, 'source_quality_allows_candidate_creation': source_allows,
            'candidate_type': candidate_type, 'candidate_type_allows_candidate_creation': type_allows,
            'quality_gate_reason': reason}
