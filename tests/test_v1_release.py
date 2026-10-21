"""Release-boundary and legacy-database regressions for the non-AI v1 app."""
import ast
from datetime import date
import os
from pathlib import Path
import secrets
import subprocess
import sys

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.db.database import Base
from app.main import app

ROOT = Path(__file__).resolve().parents[1]


def test_chat_is_not_registered_or_documented() -> None:
    assert not any(path.startswith('/chat') for path in app.openapi()['paths'])
    with TestClient(app) as client:
        for method in ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']:
            for path in ['/chat', '/chat/', '/chat/history']:
                response = client.request(method, path, json={'message': 'retired action'}, headers={'X-Confirmed-Tool-Key': 'synthetic-retired-key'})
                assert response.status_code == 404


def test_startup_with_provider_and_removed_module_imports_blocked() -> None:
    source = """
import importlib.abc, sys
class NoRetiredImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        forbidden = ('google', 'groq', 'app.core.chat', 'app.core.rag', 'app.api.routes.chat', 'app.models.conversation', 'app.schemas.chat', 'app.schemas.conversation')
        if any(fullname == name or fullname.startswith(name + '.') for name in forbidden):
            raise AssertionError('Retired integration import attempted')
sys.meta_path.insert(0, NoRetiredImports())
from app.core.rate_limit import RedisStore
RedisStore.ping = lambda self: None  # Connectivity tested against disposable Redis elsewhere.
from app.main import app
from app.core.config import SETTINGS
from fastapi.testclient import TestClient
assert not any(p.startswith('/chat') for p in app.openapi()['paths'])
assert SETTINGS.app_env == 'production'
assert not any(name in vars(SETTINGS) for name in ['chat_mock_enabled', 'gemini_api_key', 'groq_api_key', 'rag_enabled'])
with TestClient(app) as client:
    assert client.get('/health').json() == {'status': 'ok'}
    assert client.post('/chat', json={'message': 'retired'}).status_code == 404
"""
    env = {k: v for k, v in os.environ.items() if k in {'PATH', 'SYSTEMROOT', 'TMPDIR'}}
    env.update(PYTHONDONTWRITEBYTECODE='1', APP_ENV='production', JWT_SECRET_KEY=secrets.token_urlsafe(48), DATABASE_URL='sqlite:///:memory:', RATE_LIMIT_REDIS_URL='redis://127.0.0.1:1/0', RATE_LIMIT_HMAC_KEY=secrets.token_urlsafe(48))
    # Retired flags may remain in deployment configuration; they must be ignored.
    env.update(CHAT_MOCK_ENABLED='true', GEMINI_API_KEY='synthetic-not-a-credential', GROQ_API_KEY='synthetic-not-a-credential', RAG_ENABLED='invalid-retired-setting')
    result = subprocess.run([sys.executable, '-c', source], cwd=ROOT, env=env, text=True, capture_output=True)
    assert result.returncode == 0, 'Isolated no-AI startup regression failed (output suppressed)'


def test_application_has_no_retired_imports_or_provider_requirements() -> None:
    forbidden = ('app.core.chat', 'app.core.rag', 'app.models.conversation', 'app.schemas.chat', 'app.schemas.conversation', 'app.api.routes.chat', 'google', 'groq')
    for path in (ROOT / 'app').rglob('*.py'):
        for node in ast.walk(ast.parse(path.read_text())):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module] if isinstance(node, ast.ImportFrom) and node.module else []
            assert not any(name == prefix or name.startswith(prefix + '.') for name in names for prefix in forbidden), str(path)
    requirements = (ROOT / 'requirements.txt').read_text().lower()
    assert 'google-genai' not in requirements
    assert 'groq' not in requirements
    phase2d_tables = {
        'notification_preferences', 'notification_devices', 'payment_occurrences',
        'payment_occurrence_events', 'notifications', 'notification_deliveries',
    }
    assert set(Base.metadata.tables) == {
        'users', 'obligations', 'obligation_installments', 'auth_sessions',
        'auth_refresh_tokens', 'legacy_access_revocations',
        'account_id_sequence', 'admin_audit_events',
    } | phase2d_tables
    required_owners = {
        'notification_preferences': {'users.id'},
        'notification_devices': {'users.id', 'auth_sessions.id'},
        'payment_occurrences': {'users.id', 'obligations.id', 'obligation_installments.id'},
        'payment_occurrence_events': {'users.id', 'payment_occurrences.id'},
        'notifications': {'users.id', 'obligations.id', 'payment_occurrences.id'},
        'notification_deliveries': {'notifications.id', 'notification_devices.id'},
    }
    for table_name, owner_targets in required_owners.items():
        targets = {foreign_key.target_fullname for foreign_key in Base.metadata.tables[table_name].foreign_keys}
        assert owner_targets <= targets, f'{table_name} is missing ownership/parent foreign keys'
    audit_targets = {foreign_key.target_fullname for foreign_key in Base.metadata.tables['admin_audit_events'].foreign_keys}
    assert audit_targets == {'users.id'}


@pytest.fixture
def legacy_database(monkeypatch):
    # Apply existing revision history only to this disposable in-memory database.
    engine = sa.create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    monkeypatch.setattr(sa, 'engine_from_config', lambda *args, **kwargs: engine)
    config = Config(str(ROOT / 'alembic.ini'))
    config.set_main_option('script_location', str(ROOT / 'alembic'))
    command.upgrade(config, 'head')
    with Session(engine) as session:
        app.dependency_overrides[get_db] = lambda: session
        with TestClient(app) as client:
            yield engine, session, client, config
    app.dependency_overrides.clear()
    engine.dispose()


def register_login(client: TestClient, email: str) -> tuple[int, dict[str, str]]:
    registered = client.post('/auth/register', json={'name': 'Legacy compatibility', 'email': email, 'password': 'SyntheticPassword123!'})
    assert registered.status_code == 201
    assert registered.json()['monthly_income'] == '0.00'
    logged_in = client.post('/auth/login', json={'email': email, 'password': 'SyntheticPassword123!'})
    assert logged_in.status_code == 200
    assert set(logged_in.json()) == {'access_token', 'token_type'}
    return registered.json()['id'], {'Authorization': 'Bearer ' + logged_in.json()['access_token']}


def test_existing_schema_data_financial_flows_and_cross_user_access(legacy_database) -> None:
    engine, session, client, _ = legacy_database
    uid, headers = register_login(client, 'legacy-owner@example.com')
    _, foreign = register_login(client, 'legacy-other@example.com')
    session.execute(sa.text('INSERT INTO conversations (id, user_id) VALUES (:id, :user_id)'), {'id': 1, 'user_id': uid})
    session.execute(sa.text('INSERT INTO conversation_messages (conversation_id, role, content) VALUES (:id, :role, :content)'), {'id': 1, 'role': 'user', 'content': 'Synthetic archived message'})
    session.commit()
    fixture = {'provider': 'Test provider', 'item_name': 'Existing purchase', 'category': 'test', 'total_amount': '1200.00', 'monthly_installment_amount': '100.00', 'start_date': date.today().replace(day=1).isoformat(), 'term_months': 12, 'due_day_of_month': 15, 'source': 'chatbot_entry'}
    created = client.post('/obligations', headers=headers, json=fixture)
    assert created.status_code == 201  # Optional income remains optional.
    oid = created.json()['id']
    assert client.get(f'/obligations/{oid}', headers=headers).json()['source'] == 'chatbot_entry'
    for method, body in [('GET', None), ('PUT', {'item_name': 'Wrong owner'}), ('DELETE', None)]:
        assert client.request(method, f'/obligations/{oid}', headers=foreign, json=body).status_code == 404
    assert client.get('/obligations', headers=foreign).json() == []
    profile = client.patch('/auth/me', headers=headers, json={'monthly_income': '1000.00', 'fixed_expenses': '200.00'})
    assert profile.status_code == 200
    summary = client.get('/dashboard/summary', headers=headers)
    assert summary.status_code == 200
    assert summary.json()['current_month_projected_buffer'] == '700.00'
    forecast = client.get('/forecast', headers=headers, params={'start_month': fixture['start_date'], 'months': 2})
    assert forecast.status_code == 200
    assert [r['projected_buffer'] for r in forecast.json()['rows']] == ['700.00', '700.00']
    affordable = client.post('/affordability', headers=headers, json={'amount': '100.00', 'start_date': fixture['start_date'], 'term_months': 2})
    assert affordable.status_code == 200
    assert affordable.json()['worst_projected_buffer'] == '600.00'
    assert client.put(f'/obligations/{oid}', headers=headers, json={'item_name': 'Owner update'}).status_code == 200
    assert client.get(f'/obligations/{oid}', headers=headers).json()['item_name'] == 'Owner update'
    assert client.post('/chat', headers=headers, json={'message': 'delete everything'}).status_code == 404
    assert client.get(f'/obligations/{oid}', headers=headers).status_code == 200
    assert client.delete(f'/obligations/{oid}', headers=headers).status_code == 204
    assert client.get('/obligations', headers=headers).json() == []
    assert session.scalar(sa.text('SELECT count(*) FROM conversations')) == 1
    assert session.scalar(sa.text('SELECT content FROM conversation_messages')) == 'Synthetic archived message'
    assert {'conversations', 'conversation_messages'} <= set(sa.inspect(engine).get_table_names())


def test_autogenerate_does_not_propose_retained_table_drops(legacy_database) -> None:
    _, _, _, config = legacy_database
    # Executes the real env.py autogenerate configuration, not a copied filter.
    command.check(config)


def test_legacy_table_filter_does_not_hide_unrelated_schema_changes() -> None:
    from app.db.migration_policy import include_object

    for name in ['conversations', 'conversation_messages']:
        assert not include_object(None, name, 'table', True, None)
        assert include_object(None, name, 'table', True, object())
    assert include_object(None, 'unrelated_table', 'table', True, None)
    assert include_object(None, 'users', 'table', True, None)
