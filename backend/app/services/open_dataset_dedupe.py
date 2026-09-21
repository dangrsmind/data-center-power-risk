"""Snapshot duplicate index: no per-input-row database queries or 1,000-row cutoff.

Exact hashes, names, IDs and coordinate cells use indexes. Domain/state buckets
retain the legacy fuzzy/weak match rules; dense buckets may need pairwise work.
"""
import math
from collections import defaultdict
from sqlalchemy import select
from app.models.project import Project
from app.models.project_candidate import ProjectCandidate
from app.models.imported_dataset import ImportedDatasetRow
from app.services.candidate_coordinates import candidate_coordinates
from app.services.csv_candidate_dedupe import match_normalized_records, normalized_text, normalized_url, url_domain


def keys(n):
    result = set()
    for field in ('name', 'state', 'address', 'project_family'):
        if normalized_text(n.get(field)):
            result.add((field, normalized_text(n[field])))
    if n.get('external_dataset_id'):
        result.add(('external', n.get('dataset_name'), str(n['external_dataset_id'])))
    for url in n.get('source_urls') or []:
        if isinstance(url, str) and normalized_url(url):
            result.add(('url', normalized_url(url)))
            result.add(('domain', url_domain(url)))
    lat, lon = candidate_coordinates(n)
    if lat is not None:
        # Neighboring cells ensure the existing <=0.01 proximity rule is retained.
        result.add(('cell', math.floor(lat * 100), math.floor(lon * 100)))
    return result

class DuplicateIndex:
    def __init__(self, db):
        self.entries = []
        self.buckets = defaultdict(set)
        self.hashes = defaultdict(list)
        self.cities = set()
        for row in db.scalars(select(ImportedDatasetRow).order_by(ImportedDatasetRow.id)):
            n = row.normalized_row_json if isinstance(row.normalized_row_json, dict) else {}
            n = {**n, 'dataset_name': row.dataset_name}
            h = n.get('row_fingerprint')
            self.add(n, 'imported_row', str(row.id), h, compare=n.get('dataset_row_type', 'data_center') == 'data_center')
        for c in db.scalars(select(ProjectCandidate).order_by(ProjectCandidate.id)):
            raw = c.raw_metadata_json if isinstance(c.raw_metadata_json, dict) else {}
            n = raw.get('normalized_row') if isinstance(raw.get('normalized_row'), dict) else {}
            lat, lon = candidate_coordinates(raw)
            self.add({**n, 'name':c.candidate_name,'state':c.state,'city':c.city,'county':c.county,
                'developer':c.developer,'load_mw':c.load_mw,'latitude':lat,'longitude':lon,
                'source_urls':list(dict.fromkeys([*(n.get('source_urls') or []), *([c.primary_source_url] if c.primary_source_url else [])]))}, 'project_candidate',str(c.id))
        for p in db.scalars(select(Project).order_by(Project.id)):
            raw = p.candidate_metadata_json if isinstance(p.candidate_metadata_json, dict) else {}
            n = raw.get('normalized_row') if isinstance(raw.get('normalized_row'), dict) else {}
            self.add({**n,'name':p.canonical_name,'state':p.state,'county':p.county,'developer':p.developer or p.operator,
                'latitude':p.latitude,'longitude':p.longitude,'source_urls':[raw['primary_source_url']] if raw.get('primary_source_url') else n.get('source_urls',[])},'project',str(p.id))

    def add(self,n,kind,id_,hash_=None,compare=True):
        if n.get('city'): self.cities.add(n['city'])
        entry=(dict(n),kind,id_)
        if hash_: self.hashes[hash_].append(entry)
        if not compare: return
        index=len(self.entries);self.entries.append(entry)
        for k in keys(n): self.buckets[k].add(index)

    def matches(self,n,hash_,compare=True):
        if hash_ in self.hashes:
            return [{'record_type':k,'record_id':id_,'status':'exact_duplicate','reasons':['same_source_row_hash']}
                    for _,k,id_ in self.hashes[hash_]]
        if not compare: return []
        candidates=set()
        for key in keys(n):
            candidates.update(self.buckets[key])
            if key[0]=='cell':
                for x in (-1,0,1):
                    for y in (-1,0,1): candidates.update(self.buckets[('cell',key[1]+x,key[2]+y)])
        matches=[]
        for i in sorted(candidates):
            other,kind,id_=self.entries[i]
            m=match_normalized_records(n,other,record_type=kind,record_id=id_)
            if m.status != 'distinct': matches.append(m.to_dict())
            elif normalized_text(n.get('name')) and normalized_text(n.get('name'))==normalized_text(other.get('name')) and any(n.get(k) and normalized_text(n[k])==normalized_text(other.get(k)) for k in ('state','country')):
                matches.append({'record_type':kind,'record_id':id_,'status':'possible_duplicate','reasons':['same_name_location']})
        return matches
