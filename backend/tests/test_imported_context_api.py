import uuid
from datetime import datetime, timedelta, timezone
import pytest
from fastapi import FastAPI
import asyncio
import json
from urllib.parse import urlencode
from types import SimpleNamespace
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.api.routes.imported_context import router
from app.models import Base
from app.models.imported_dataset import ImportedDatasetRun, ImportedDatasetRow
from app.models.project_candidate import ProjectCandidate

@pytest.fixture()
def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        run = ImportedDatasetRun(dataset_name='epoch', source_file='data.csv')
        candidate = ProjectCandidate(candidate_key='test', candidate_name='Linked facility', confidence=.6)
        db.add_all([run, candidate]); db.flush()
        for i in range(4):
            db.add(ImportedDatasetRow(run_id=run.id, dataset_name='epoch' if i < 3 else 'other',
                source_file='/one/chillers.csv' if i < 2 else '/two/timelines.csv', row_number=i+1,
                raw_row_json={'name': f'Facility {i}', 'literal': '100%_value'},
                normalized_row_json={'dataset_row_type': 'equipment', 'name': f'Cooling {i}'},
                source_urls_json=['https://example.org/audit'], duplicate_status='unique' if i < 2 else 'duplicate',
                warnings_json=['warning'] if i == 0 else ([] if i < 3 else None),
                errors_json=['error'] if i == 1 else None,
                linked_project_candidate_id=candidate.id if i == 0 else None,
                created_at=datetime.now(timezone.utc)-timedelta(days=i)))
        db.commit()
    def prohibit_writes(conn, cursor, statement, parameters, context, executemany):
        assert statement.lstrip().split()[0].upper() in ('SELECT', 'PRAGMA'), statement
    event.listen(engine, 'before_cursor_execute', prohibit_writes)
    app = FastAPI(); app.include_router(router)
    def session():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = session
    class Client:
        def request(self, method, path, params=None, **kwargs):
            messages = []
            async def receive():
                return {"type": "http.request", "body": b"", "more_body": False}
            async def send(message):
                messages.append(message)
            scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                     "method": method, "scheme": "http", "path": path, "raw_path": path.encode(),
                     "query_string": urlencode(params or {}).encode(), "headers": [],
                     "client": ("test", 123), "server": ("test", 80), "root_path": ""}
            asyncio.run(app(scope, receive, send))
            body = b"".join(m.get("body", b"") for m in messages)
            return SimpleNamespace(status_code=messages[0]["status"], json=lambda: json.loads(body))
        def get(self, path, params=None):
            return self.request("GET", path, params)
    yield Client()
    engine.dispose()


def test_list_pagination_detail(client):
    first = client.get('/imported-context', params={'limit': 2}).json()
    second = client.get('/imported-context', params={'limit': 2, 'offset': 2}).json()
    assert first['total'] == second['total'] == 4
    assert [r['row_number'] for r in first['items']+second['items']] == [1,2,3,4]
    assert 'raw_row_json' not in first['items'][0]
    detail = client.get('/imported-context/'+first['items'][0]['id']).json()
    assert detail['raw_row_json']['name'] == 'Facility 0'
    assert detail['normalized_row_json']['dataset_row_type'] == 'equipment'
    assert detail['source_urls_json'] == ['https://example.org/audit']
    assert detail['warnings_json'] == ['warning']
    assert detail['linked_candidate']['candidate_name'] == 'Linked facility'
    assert detail['display_name'] == 'Cooling 0'
    assert client.get('/imported-context/'+str(uuid.uuid4())).status_code == 404
    assert client.get('/imported-context/no-uuid').status_code == 422
    for params in [{'limit': 0}, {'limit': 201}, {'offset': -1}]:
        assert client.get('/imported-context', params=params).status_code == 422

@pytest.mark.parametrize('params,count', [
    ({'dataset_name':'epoch'},3), ({'source_file':'CHILLERS'},2), ({'duplicate_status':'duplicate'},2),
    ({'has_candidate':'true'},1), ({'has_candidate':'false'},3), ({'has_warnings':'true'},1),
    ({'has_warnings':'false'},3), ({'has_errors':'true'},1), ({'has_errors':'false'},3),
    ({'q':'Facility 0'},1), ({'q':'Cooling 1'},1), ({'q':'example.org'},4),
    ({'q':'100%_value'},4), ({'q':'100%_missing'},0), ({'source_file':'%'},0),
    ({'dataset_name':'epoch','has_errors':'true'},1),
])
def test_filters(client, params, count):
    response = client.get('/imported-context', params=params)
    assert response.status_code == 200
    assert response.json()['total'] == count

def test_summary(client):
    result = client.get('/imported-context/summary').json()
    assert result['total'] == 4
    assert result['counts_by_dataset_name'] == {'epoch':3,'other':1}
    assert result['counts_by_source_file'] == {'chillers.csv':2,'timelines.csv':2}
    assert result['counts_by_duplicate_status'] == {'unique':2,'duplicate':2}
    assert result['rows_with_warnings'] == result['rows_with_errors'] == result['linked_candidate_count'] == 1
    assert result['recent_row_count'] == 4
    assert len(result['recent_rows']) == 4
    assert result['top_source_files'][0] == {'source_file':'chillers.csv','count':2}

def test_read_only_http_contract(client):
    for path in ['/imported-context','/imported-context/summary','/imported-context/'+str(uuid.uuid4())]:
        for method in ['POST','PATCH','PUT','DELETE']:
            assert client.request(method,path,json={}).status_code == 405
