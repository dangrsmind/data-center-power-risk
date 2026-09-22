"""Explainable local-only triage and bounded atomic writes. No verification or Evidence."""
import csv
import io
import hashlib
import json
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import select, text
from app.core.enums import LifecycleState
from app.models.project import Project
from app.models.imported_dataset import ImportedDatasetRun, ImportedDatasetRow, ImportedCandidateLink
from app.services.baseline_dataset_profiles import normalize_baseline_row, fingerprint, public_url, filename_warning
from app.services.baseline_source_quality import classify_source_and_candidate
from app.services.baseline_source_row_alignment import classify_source_row_alignment, primary_source_text, contains
from app.services.baseline_entity_taxonomy import classify_entity_taxonomy, lifecycle, words
from app.services.candidate_coordinates import candidate_coordinates
from app.services.csv_dataset_importer import build_project_candidate, STATE_BY_NAME
from app.services.csv_candidate_dedupe import normalized_text
from app.services.open_dataset_registry import REGISTRY, DECISIONS
from app.services.open_dataset_dedupe import DuplicateIndex

VERSION = 'open-ingest-v0.1'

def decide(row, policy, matches, cities):
    n=row.normalized
    urls=row.source_urls
    provenance=bool(urls or (policy.canonical_source_url and public_url(policy.canonical_source_url)))
    quality=classify_source_and_candidate(urls[0] if urls else None,n)
    quality['quality_gate_reason']=quality['quality_gate_reason'].replace(
        '; analyst source review still required.', '; offline source hint, not verification.')
    alignment=classify_source_row_alignment(n,urls,row.raw_row,known_cities=cities)
    taxonomy=classify_entity_taxonomy(n,quality,urls,row.raw_row)
    stage=lifecycle(words(n.get('lifecycle_state')))
    lat,lon=candidate_coordinates(n)
    location=bool(n.get('state') or n.get('city') or n.get('country') or n.get('address'))
    project_type=n['dataset_row_type']=='data_center'
    context=not project_type or taxonomy['candidate_purpose'] in {'facility_baseline','infrastructure_context','supply_chain_signal','permitting_or_policy_signal'} or stage=='existing_operational'
    exact=any(m['status']=='exact_duplicate' for m in matches)
    ambiguous=bool(matches) and not exact
    source_text,_=primary_source_text(urls[0] if urls else None,n,row.raw_row,urls)
    source_states={code for name,code in STATE_BY_NAME.items() if contains(source_text,name)}
    if contains(source_text,'west virginia'): source_states.discard('VA')
    explicit_state_conflict=bool(n.get('state') and source_states and n['state'] not in source_states)
    mismatch=explicit_state_conflict or alignment['source_row_alignment'] in {'geography_mismatch','facility_or_operator_mismatch'}
    invalid_coords=any('latitude' in e or 'longitude' in e for e in row.errors+row.warnings)
    quality_ok=quality['source_quality_allows_candidate_creation'] and quality['candidate_type_allows_candidate_creation']
    aligned=alignment['source_row_alignment_allows_candidate_creation']
    scores=dict(source_trust_score=policy.source_trust_score if provenance else 0,
        identity_score=1.0 if n.get('name') else 0,
        location_score=1.0 if n.get('state') and n.get('city') else 0.65 if location else 0,
        coordinate_score=1.0 if lat is not None else 0,
        lifecycle_score=1.0 if stage in {'proposed','under_construction','planned_expansion','existing_operational'} else 0,
        source_specificity_score=1.0 if quality_ok and aligned else 0.4 if urls else 0,
        duplicate_risk_score=1.0 if exact else 0.7 if ambiguous else 0,
        conflict_score=1.0 if mismatch else 0.5 if invalid_coords else 0)
    overall=sum(scores[k]*w for k,w in [('source_trust_score',.20),('identity_score',.20),('location_score',.15),
        ('coordinate_score',.15),('lifecycle_score',.15),('source_specificity_score',.15)])
    scores['overall_confidence']=round(max(0,overall-.3*scores['duplicate_risk_score']-.3*scores['conflict_score']),4)
    reasons=[]
    warnings=[w for w in row.warnings if w!='baseline_dataset_import_requires_analyst_review']+list(row.errors)
    if not policy.license_url: warnings.append('license_unknown: automatic Project creation disabled')
    auto_gates={
        'dataset_policy':policy.auto_project_allowed,
        'public_provenance':provenance,
        'identity':bool(n.get('name')),
        'state_location':n.get('state') in set(STATE_BY_NAME.values()),
        'coordinates':lat is not None,
        'active_lifecycle':stage in {'proposed','under_construction','planned_expansion'},
        'source_quality':quality_ok,
        'specific_primary_alignment':alignment['source_row_alignment']=='aligned',
        'direct_primary_source':quality['source_quality'] in {'official_project_or_operator','government_or_regulatory'},
        'no_duplicate':not matches,
        'no_conflict':not mismatch and not invalid_coords,
        'no_blocking_warnings':not warnings,
        'confidence':scores['overall_confidence']>=policy.auto_project_threshold,
    }
    if not any(str(v or '').strip() for v in row.raw_row.values()):
        decision='reject_or_ignore';reasons=['Empty row; no usable entity or context.']
    elif not provenance:
        decision='reject_or_ignore';reasons=['No public source/provenance; no durable row will be written.']
    elif exact:
        decision='skip_duplicate';reasons=['Existing representation or identical audited source row; no merge or new row.']
    elif alignment['source_row_alignment']=='cancelled_or_rejected_project' or stage in {'cancelled','retired'}:
        decision='reject_or_ignore';reasons=['Cancelled, rejected or retired without active project signal.']
    elif mismatch or ambiguous:
        decision='exception_review';reasons=([f'Explicit primary-source state conflicts with row state {n.get("state")}.'] if explicit_state_conflict else alignment['source_row_alignment_reasons']) if mismatch else ['Uncertain duplicate; do not silently merge or create.']
    elif context and policy.context_allowed:
        decision='create_context_record_only';reasons=['Useful facility/infrastructure/timeline/equipment context; not an active build Project.']
    elif not n.get('name') or not location or row.errors or invalid_coords:
        decision='exception_review';reasons=['Critical identity/location/coordinate validation failed.']
    elif not quality_ok or not aligned or stage not in {'proposed','under_construction','planned_expansion'}:
        decision='exception_review';reasons=[quality['quality_gate_reason'],*alignment['source_row_alignment_reasons'],'Explicit active lifecycle required for project/candidate creation.']
    elif all(auto_gates.values()):
        decision='auto_create_project';reasons=['Dataset policy, direct primary source, identity, alignment, lifecycle and duplicate gates all passed.']
    elif scores['overall_confidence']>=policy.candidate_threshold:
        decision='create_project_candidate';reasons=['Plausible build with public primary source; automatic Project gates not all met.',
            'Failed automatic gates: '+', '.join(k for k,v in auto_gates.items() if not v)]
    else:
        decision='exception_review';reasons=['Below candidate confidence threshold.']
    if decision not in policy.allowed_automated_outcomes:
        decision='reject_or_ignore';reasons=['Decision lane disabled by dataset policy.']
    return dict(**scores,decision=decision,decision_reasons=reasons,warnings=sorted(set(warnings)),
        duplicate_matches=matches,auto_project_gates=auto_gates,source_quality=quality,source_row_alignment=alignment,
        taxonomy=taxonomy,inferred_record_type=n['dataset_row_type'] if not project_type else taxonomy['entity_type'],
        source_row_hash=n['row_fingerprint'],
        normalized_identity_key=fingerprint({'name':normalized_text(n.get('name')),'location':[normalized_text(n.get(k)) for k in ('city','state','country')]}),
        normalized_location_key=fingerprint({k:n.get(k) for k in ('state','city','country','latitude','longitude')}),
        engine_version=VERSION,source_url=urls[0] if urls else policy.canonical_source_url,
        dataset_id=policy.dataset_id,source_file=row.source_file,row_number=row.row_number,source_row_id=n.get('external_dataset_id'))


def _ingest_open_dataset(db, *, dataset, inputs, confirm=False, max_create_projects=None,
                        max_create_candidates=None, max_write_rows=None, limit=None, include_row_details=False):
    policy=REGISTRY[dataset]
    if not (0 <= policy.candidate_threshold < policy.auto_project_threshold <= 1):
        raise ValueError('Invalid registry confidence thresholds')
    caps=(max_create_projects,max_create_candidates,max_write_rows)
    if any(v is not None and (type(v) is not int or v<0) for v in caps): raise ValueError('Caps must be nonnegative integers')
    if confirm and any(v is None for v in caps): raise ValueError('Confirmation requires all three explicit caps; nothing written')
    if limit is not None and (type(limit) is not int or limit<0): raise ValueError('limit must be nonnegative')
    paths=[Path(p).resolve() for p in inputs]
    if not paths: raise ValueError('At least one explicit local input file is required')
    if any(not p.is_file() for p in paths): raise ValueError('Input must be an existing local file')
    # Planning must not flush incidental pending ORM state. Confirm owns its transaction.
    if db.new or db.dirty or db.deleted: raise ValueError('Use a clean session for automated ingestion')
    index=DuplicateIndex(db)
    normalized=[];files=[]
    for path in paths:
        if filename_warning(dataset,str(path)): raise ValueError(f'Unregistered filename for {dataset}: {path.name}')
        payload=path.read_bytes()
        files.append({'path':str(path),'sha256':hashlib.sha256(payload).hexdigest()})
        # Parse exactly the bytes hashed, even if the source file changes later.
        with io.StringIO(payload.decode('utf-8-sig'),newline='') as handle:
            reader=csv.DictReader(handle)
            if not reader.fieldnames or len(set(reader.fieldnames))!=len(reader.fieldnames): raise ValueError('Missing or duplicate CSV header')
            for number,raw in enumerate(reader,start=2):
                if limit is not None and len(normalized)>=limit: break
                if None in raw or any(v is None for v in raw.values()): raise ValueError(f'Malformed CSV row {number} in {path.name}')
                row=normalize_baseline_row(dataset,raw,source_file=str(path),import_run_id='preview',
                    source_url=policy.canonical_source_url,citation=policy.attribution_text,license_note=policy.license_summary)
                row.row_number=number
                normalized.append(row)
                if row.normalized.get('city'): index.cities.add(row.normalized['city'])
    plans=[];counts=Counter();hist=Counter();examples=defaultdict(list);clusters=[]
    for row in normalized:
        n=row.normalized
        matches=index.matches(n,n['row_fingerprint'],compare=n['dataset_row_type']=='data_center')
        result=decide(row,policy,matches,index.cities)
        plans.append((row,result));counts[result['decision']]+=1
        score=result['overall_confidence'];hist['high_0.85_to_1' if score>=.85 else 'medium_0.60_to_0.85' if score>=.60 else 'low_below_0.60']+=1
        if len(examples[result['decision']])<5: examples[result['decision']].append({'name':n.get('name'),**result})
        if matches and len(clusters)<100: clusters.append({'source_row_hash':result['source_row_hash'],'matches':matches[:10]})
        index.add(n,'input_row',f'{row.source_file}:{row.row_number}',n['row_fingerprint'],compare=n['dataset_row_type']=='data_center')
    durable=[(r,d) for r,d in plans if d['decision'] not in {'skip_duplicate','reject_or_ignore'}]
    projects=counts['auto_create_project'];candidates=counts['create_project_candidate']
    # Count every inserted DB row: run + audit + entity + link. No silent truncation.
    writes=(1 if durable else 0)+len(durable)+2*(projects+candidates)
    cap_checks={'projects':max_create_projects is None or projects<=max_create_projects,
                'candidates':max_create_candidates is None or candidates<=max_create_candidates,
                'rows':max_write_rows is None or writes<=max_write_rows}
    invalid_rows=sum(bool(r.errors) or any('latitude' in w or 'longitude' in w for w in r.warnings) for r,_ in plans)
    report={'dataset_id':dataset,'source_files':files,'dry_run':not confirm,'input_row_limit':limit,
        'registry_policy':policy.snapshot(),'engine_version':VERSION,'rows_read':len(plans),
        'rows_valid':len(plans)-invalid_rows,'rows_invalid':invalid_rows,
        'rows_with_coordinates':sum(candidate_coordinates(r.normalized)[0] is not None for r,_ in plans),
        'rows_missing_coordinates':sum(candidate_coordinates(r.normalized)[0] is None for r,_ in plans),
        'decisions_by_type':{k:counts[k] for k in DECISIONS},'confidence_distribution':dict(hist),
        'would_create_projects':projects,'would_create_project_candidates':candidates,
        'would_create_context_records':counts['create_context_record_only'],'would_skip_duplicates':counts['skip_duplicate'],
        'would_exception_review':counts['exception_review'],'would_reject_or_ignore':counts['reject_or_ignore'],
        'would_write_rows':writes,'caps':dict(zip(('max_create_projects','max_create_candidates','max_write_rows'),caps)),
        'within_caps':cap_checks,'duplicate_clusters':clusters,'duplicate_clusters_truncated':sum(bool(d['duplicate_matches']) for _,d in plans)>100,
        'warnings':sorted({w for _,d in plans for w in d['warnings']}),'top_examples':dict(examples),
        'created_projects':0,'created_project_candidates':0,'written_rows':0}
    if include_row_details: report['row_details']=[{'name':r.normalized.get('name'),**d} for r,d in plans]
    if not confirm: return report
    if not all(cap_checks.values()): raise ValueError(f'Creation/write caps exceeded: planned projects={projects}, candidates={candidates}, rows={writes}; nothing written')
    if not durable: return report
    run=ImportedDatasetRun(id=uuid.uuid4(),dataset_name=dataset,source_file='; '.join(str(p) for p in paths),
        dry_run=False,dataset_source=policy.canonical_source_url,citation=policy.attribution_text,license_note=policy.license_summary,
        summary_json={k:v for k,v in report.items() if k!='row_details'})
    try:
        audits_to_write=[];entities_to_write=[];links_to_write=[]
        for row,decision in durable:
            n=row.normalized
            row.normalized={**n,'import_run_id':str(run.id),'automated_ingestion':decision}
            audit=ImportedDatasetRow(id=uuid.uuid4(),run_id=run.id,dataset_name=dataset,dataset_source=row.dataset_source,
                source_file=row.source_file,row_number=row.row_number,raw_row_json=row.raw_row,
                normalized_row_json=row.to_persisted_normalized(),source_urls_json=row.source_urls,
                duplicate_status='possible_duplicate' if decision['duplicate_matches'] else 'distinct',
                warnings_json=decision['warnings'],errors_json=row.errors)
            audits_to_write.append(audit)
            metadata={'provenance':'dataset_import','dataset_id':dataset,'dataset_name':dataset,'import_kind':'automated_open_dataset_import',
                'import_run_id':str(run.id),'imported_row_id':str(audit.id), 'source_file':row.source_file,'row_number':row.row_number,
                'primary_source_url':decision['source_url'],'source_urls':row.source_urls,'normalized_row':row.normalized,
                'automated_ingestion':decision,'registry_policy':policy.snapshot(),
                'imported_rows':[{'imported_row_id':str(audit.id),'import_run_id':str(run.id),'dataset_name':dataset}]}
            entity=None;kind=None
            if decision['decision']=='auto_create_project':
                lat,lon=candidate_coordinates(n)
                entity=Project(id=uuid.uuid4(),canonical_name=n['name'][:255],state=n['state'],county=n.get('county'),developer=n.get('developer'),
                    lifecycle_state=LifecycleState.CANDIDATE_UNVERIFIED,latitude=lat,longitude=lon,
                    coordinate_status='unverified',coordinate_precision='source_row',coordinate_source=dataset,
                    coordinate_source_url=decision['source_url'],coordinate_confidence=decision['overall_confidence'],
                    coordinate_updated_at=datetime.now(timezone.utc),candidate_metadata_json=metadata)
                kind='project'
            elif decision['decision']=='create_project_candidate':
                entity=build_project_candidate(row,'open-dataset:'+decision['source_row_hash']);entity.id=uuid.uuid4()
                entity.confidence=decision['overall_confidence'];entity.lifecycle_state='dataset_import_needs_review';entity.claim_count=0
                entity.raw_metadata_json={**entity.raw_metadata_json,**metadata};kind='project_candidate'
            if entity:
                entities_to_write.append(entity)
                links_to_write.append(ImportedCandidateLink(id=uuid.uuid4(),imported_row_id=audit.id,linked_record_type=kind,
                    linked_record_id=entity.id,duplicate_status='distinct',match_reasons_json=decision['decision_reasons']))
        # Explicit dependency order also works with enforced PostgreSQL/SQLite FKs.
        db.add(run);db.flush()
        db.add_all(audits_to_write+entities_to_write);db.flush()
        db.add_all(links_to_write);db.flush()
        report.update(created_projects=projects,created_project_candidates=candidates,written_rows=writes)
        run.summary_json={k:v for k,v in report.items() if k!='row_details'}
        db.commit()
    except Exception:
        db.rollback();raise
    return report


def ingest_open_dataset(db, **kwargs):
    """Serialize this pipeline's confirmed planners and roll back every failure."""
    confirm=kwargs.get('confirm',False)
    if db.new or db.dirty or db.deleted:
        raise ValueError('Use a clean session for automated ingestion')
    try:
        with db.no_autoflush:
            if confirm:
                dialect=db.get_bind().dialect.name
                if dialect=='sqlite': db.execute(text('BEGIN IMMEDIATE'))
                elif dialect=='postgresql': db.execute(text('SELECT pg_advisory_xact_lock(746281930)'))
                else: raise ValueError('Confirmed mode supports SQLite/PostgreSQL only')
            result=_ingest_open_dataset(db,**kwargs)
            if confirm: db.commit()
            return result
    except Exception:
        if confirm: db.rollback()
        raise
