"""Crash recovery, schema upgrades, verified backups and offline PC replication."""
import asyncio
import json
from pathlib import Path
import shutil
import time
from unittest.mock import AsyncMock

import pytest

from app.db import Database
from app.services import operations, prediction_analytics as forecasts
from app.utils import backup
from app.utils.process_lock import ProcessLock
from scripts import backup_pull


async def forecast_row(database, key='recover'):
    await database.conn.execute("INSERT INTO prediction_analytics(id,season,round,session,created_at,created_by) VALUES(?,2026,1,'race',?,1)", (key,time.time()))
    await database.conn.commit()


async def fetch(database, key='recover'):
    return dict(await (await database.conn.execute('SELECT * FROM prediction_analytics WHERE id=?',(key,))).fetchone())


async def test_existing_database_upgrades_without_rewriting_data(tmp_path):
    from app.migrations.legacy import initialize_legacy_schema
    database = Database(tmp_path/'old.db')
    await database.connect()
    try:
        await initialize_legacy_schema(database.conn)
        await forecast_row(database)
        await database.init_tables()
        await database.init_tables()
        assert (await fetch(database))['status'] == 'pending'
        assert (await fetch(database))['attempts'] == 0
        assert [r[0] for r in await (await database.conn.execute('SELECT version FROM schema_migrations ORDER BY version')).fetchall()] == [1,2]
    finally:
        await database.close()


async def test_runtime_requires_migration_in_production(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_AUTO_MIGRATE','false')
    database = Database(tmp_path/'empty.db')
    try:
        with pytest.raises(RuntimeError,match='app.migrate'):
            await database.initialize()
        await database.init_tables()
        await database.initialize()
    finally:
        await database.close()


def test_single_process_ownership_is_released_after_exit(tmp_path):
    path = tmp_path/'worker.lock'
    with ProcessLock(path):
        assert not ProcessLock(path).acquire()
    with ProcessLock(path):
        pass


async def test_concurrent_workers_only_calculate_once(db_session, monkeypatch):
    await forecast_row(db_session)
    async def calculate(*args, **kwargs):
        await asyncio.sleep(.03)
        return {'start_at':time.time()+1000,'cutoff':time.time()}
    calculate = AsyncMock(side_effect=calculate)
    monkeypatch.setattr(forecasts,'build_forecast',calculate)
    assert sorted(await asyncio.gather(forecasts.run_job(),forecasts.run_job())) == [False,True]
    assert calculate.await_count == 1
    assert (await fetch(db_session))['status'] == 'ready'


async def test_snapshot_survives_failure_and_retry_never_refetches_inputs(db_session, monkeypatch):
    await forecast_row(db_session)
    created = (await fetch(db_session))['created_at']
    snapshot = {'start_at':time.time()+1000,'cutoff':created,'inputs':{'fixture':'immutable'}}
    prepare = AsyncMock(return_value=snapshot)
    monkeypatch.setattr(forecasts,'prepare_forecast',prepare)
    def interrupted(snapshot):
        raise RuntimeError('machine stopped')
    monkeypatch.setattr(forecasts,'finish_forecast',interrupted)
    await forecasts.run_job()
    first = await fetch(db_session)
    assert first['status'] == 'pending' and first['lease_token'] is None
    assert json.loads(first['snapshot']) == snapshot
    assert prepare.call_args.kwargs['cutoff'] == created
    await db_session.conn.execute('UPDATE prediction_analytics SET next_attempt=0')
    await db_session.conn.commit()
    monkeypatch.setattr(forecasts,'prepare_forecast',AsyncMock(side_effect=AssertionError('must not refetch')))
    monkeypatch.setattr(forecasts,'finish_forecast',lambda frozen:{**frozen,'model':{'fixture':'result'}})
    await forecasts.run_job()
    result = await fetch(db_session)
    assert result['status'] == 'ready' and result['attempts'] == 2
    assert json.loads(result['payload'])['inputs'] == snapshot['inputs']
    assert json.loads(result['payload'])['cutoff'] == created


async def test_shutdown_releases_job_and_abandoned_lease_recovers(db_session, monkeypatch):
    await forecast_row(db_session)
    entered = asyncio.Event()
    async def calculate(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(forecasts,'build_forecast',calculate)
    task = asyncio.create_task(forecasts.run_job())
    await asyncio.wait_for(entered.wait(),2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (await fetch(db_session))['lease_until'] == 0
    await db_session.conn.execute("UPDATE prediction_analytics SET lease_token='dead-process',lease_until=?", (time.time()-1,))
    await db_session.conn.commit()
    monkeypatch.setattr(forecasts,'build_forecast',AsyncMock(return_value={'start_at':time.time()+1000}))
    await forecasts.run_job()
    assert (await fetch(db_session))['status'] == 'ready'


async def test_stale_worker_cannot_overwrite_new_owner_result(db_session, monkeypatch):
    await forecast_row(db_session)
    entered, finish = asyncio.Event(), asyncio.Event()
    async def stale(*args, **kwargs):
        entered.set()
        await finish.wait()
        return {'start_at':time.time()+1000,'winner':'stale'}
    monkeypatch.setattr(forecasts,'build_forecast',stale)
    first = asyncio.create_task(forecasts.run_job())
    await asyncio.wait_for(entered.wait(),2)
    await db_session.conn.execute('UPDATE prediction_analytics SET lease_until=0')
    await db_session.conn.commit()
    monkeypatch.setattr(forecasts,'build_forecast',AsyncMock(return_value={'start_at':time.time()+1000,'winner':'new'}))
    await forecasts.run_job()
    finish.set()
    await first
    assert json.loads((await fetch(db_session))['payload'])['winner'] == 'new'


async def test_frozen_forecast_closes_after_session_start_without_new_network(db_session, monkeypatch):
    await forecast_row(db_session)
    await db_session.conn.execute('UPDATE prediction_analytics SET snapshot=?', (json.dumps({'start_at':time.time()-1}),))
    await db_session.conn.commit()
    prepare = AsyncMock(side_effect=AssertionError('must not fetch'))
    monkeypatch.setattr(forecasts,'prepare_forecast',prepare)
    await forecasts.run_job()
    row = await fetch(db_session)
    assert row['status'] == 'error' and row['payload'] is None
    assert 'Сессия началась' in row['error']
    prepare.assert_not_awaited()


async def test_verified_backup_retains_all_unreplicated_copies(db_session, monkeypatch, tmp_path):
    monkeypatch.setenv('BACKUP_DIR',str(tmp_path/'backups'))
    monkeypatch.setenv('BACKUP_KEEP','1')
    await forecast_row(db_session)
    first, second, third = [await asyncio.to_thread(backup.create_backup) for _ in range(3)]
    directory = backup.backup_directory()
    assert len(list(directory.glob('backup_*.db.gz'))) == 3
    backup.verify_backup(directory/first['name'])
    (directory/first['name']).with_suffix('.replicated').write_text(first['sha256'])
    backup.clean_old_backups(1)
    assert not (directory/first['name']).exists()
    assert (directory/second['name']).exists() and (directory/third['name']).exists()
    assert backup.backup_status()['pending_replication'] == 2


async def test_backup_verification_failure_does_not_publish_snapshot(db_session,monkeypatch,tmp_path):
    monkeypatch.setenv('BACKUP_DIR',str(tmp_path/'backups'))
    def fail(path):
        raise RuntimeError('restore failed')
    monkeypatch.setattr(backup,'verify_backup',fail)
    with pytest.raises(RuntimeError):
        await asyncio.to_thread(backup.create_backup)
    assert not list(backup.backup_directory().glob('backup_*'))


class Remote:
    def __init__(self, directory, manifest):
        self.directory, self.manifest = directory, manifest
        self.acknowledged = []
        self.downloads = 0

    def list(self):
        return [self.manifest]

    def download(self, name, target):
        self.downloads += 1
        shutil.copyfile(self.directory/name,target)

    def acknowledge(self,name,digest):
        self.acknowledged.append((name,digest))


async def test_offline_pc_waits_then_transfers_and_lost_ack_does_not_redownload(db_session,monkeypatch,tmp_path):
    monkeypatch.setenv('BACKUP_DIR',str(tmp_path/'server'))
    manifest = await asyncio.to_thread(backup.create_backup)
    remote = Remote(backup.backup_directory(),manifest)
    destination = tmp_path/'offline-drive'
    assert backup_pull.sync(remote,destination) == 0
    assert not destination.exists() and remote.downloads == 0
    destination.mkdir()
    assert backup_pull.sync(remote,destination) == 1
    assert backup_pull.sync(remote,destination) == 1
    assert remote.downloads == 1 and len(remote.acknowledged) == 2
    assert backup_pull.digest(destination/manifest['name']) == manifest['sha256']


def test_corrupt_transfer_is_not_acknowledged(tmp_path):
    server,destination = tmp_path/'server',tmp_path/'pc'
    server.mkdir(); destination.mkdir()
    name='backup_20261020T120000000000Z.db'
    (server/name).write_bytes(b'invalid database')
    manifest={'name':name,'sha256':backup_pull.digest(server/name),'bytes':16,'verified':True}
    remote=Remote(server,manifest)
    with pytest.raises(Exception):
        backup_pull.sync(remote,destination)
    assert not remote.acknowledged and not (destination/name).exists()


async def test_worker_status_detects_stale_process_and_job_failures(db_session,monkeypatch):
    await operations.component('worker','test-instance',starting=True)
    assert operations.worker_ready(db_session.db_path)
    await operations.register_job('fixture',5)
    async def fail():
        raise ValueError('provider secret')
    with pytest.raises(ValueError):
        await operations.run_tracked('fixture',fail)
    result=await operations.status()
    assert result['worker_healthy'] and result['jobs'][0]['error'] == 'ValueError'
    assert 'provider secret' not in json.dumps(result)
    await db_session.conn.execute('UPDATE runtime_components SET heartbeat=?',(time.time()-100,))
    await db_session.conn.commit()
    assert not operations.worker_ready(db_session.db_path)
    assert not (await operations.status())['worker_healthy']


async def test_payload_retention_preserves_deduplication(db_session,monkeypatch):
    from app.services import telegram_outbox as queue
    old=time.time()-40*86400
    await queue.enqueue('old','body',None,[],old,payload={'actions':['large-binary']})
    await queue.prune_payloads()
    await queue.enqueue('old','new body',None,[],time.time()+100,payload={'actions':['resend']})
    row=await (await db_session.conn.execute("SELECT text FROM telegram_delivery_batches WHERE event_key='old'")).fetchone()
    assert row[0] == ''
    payload=await (await db_session.conn.execute("SELECT channel,payload FROM delivery_payloads WHERE event_key='old'")).fetchone()
    assert tuple(payload) == ('telegram','{}')
