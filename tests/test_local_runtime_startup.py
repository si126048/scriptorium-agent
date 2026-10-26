from pathlib import Path
from types import SimpleNamespace
import subprocess
from unittest.mock import Mock
import pytest
from scriptorium.research import local_runtime as runtime


def test_waits_while_socket_accepts_but_database_rejects(tmp_path, monkeypatch):
    child = SimpleNamespace(poll=lambda: None)
    probe = Mock(side_effect=[subprocess.CompletedProcess([], code, b'', b'') for code in [2, 1, 1, 0]])
    monkeypatch.setattr(runtime.subprocess, 'run', probe)
    monkeypatch.setattr(runtime.time, 'sleep', lambda _: None)
    runtime.wait_postgres(tmp_path, Path('postgres/bin'), 55433, child, tmp_path / 'stop')
    assert probe.call_count == 4
    assert all('pg_isready.exe' in call.args[0][0] for call in probe.call_args_list)


def test_database_exit_does_not_retry_sql(tmp_path, monkeypatch):
    probe = Mock()
    monkeypatch.setattr(runtime.subprocess, 'run', probe)
    with pytest.raises(RuntimeError, match='LOCAL_POSTGRES_EXITED'):
        runtime.wait_postgres(tmp_path, tmp_path, 55433, SimpleNamespace(poll=lambda: 1), tmp_path / 'stop')
    probe.assert_not_called()


def test_wait_cancellation_keeps_cluster(tmp_path):
    stop = tmp_path / 'stop'; stop.touch()
    with pytest.raises(RuntimeError, match='LOCAL_START_CANCELLED'):
        runtime.wait_postgres(tmp_path, tmp_path, 55433, SimpleNamespace(poll=lambda: None), stop)
    assert stop.exists()


def test_wait_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime.time, 'monotonic', Mock(side_effect=[0, 1]))
    with pytest.raises(RuntimeError, match='LOCAL_POSTGRES_READY_TIMEOUT'):
        runtime.wait_postgres(tmp_path, tmp_path, 55433, SimpleNamespace(poll=lambda: None), tmp_path / 'stop', timeout=1)


def test_windows_message_decoding_and_sql_failures(monkeypatch):
    import locale
    monkeypatch.setattr(locale, 'getpreferredencoding', lambda _: 'cp936')
    message = '连接失败：数据库仍在启动'
    assert runtime.decode_output(message.encode('gb18030')) == message
    assert runtime.decode_output(message.encode('utf-8')) == message
    monkeypatch.setattr(runtime.subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess([], 2, b'', message.encode('gb18030')))
    with pytest.raises(RuntimeError, match=message):
        runtime.run(['psql.exe'])


def test_invalid_probe_fails_instead_of_retrying(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime.subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess([], 3, b'', b'invalid parameter'))
    with pytest.raises(RuntimeError, match='LOCAL_POSTGRES_PROBE_FAILED'):
        runtime.wait_postgres(tmp_path, tmp_path, 55433, SimpleNamespace(poll=lambda: None), tmp_path / 'stop')
