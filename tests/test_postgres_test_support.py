import getpass
import subprocess

import pytest

from tests.postgres_test_support import initialize_disposable_postgres


def test_failed_initdb_reports_error_and_redacts_local_identity_and_paths(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setattr(
        "tests.postgres_test_support.subprocess.run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=["initdb"], returncode=1,
            stdout=f'owned by user "{getpass.getuser()}"\n'
                   f"could not initialize {tmp_path}/data\nFATAL: shared memory unavailable\n",
        ),
    )

    with pytest.raises(pytest.fail.Exception) as error:
        initialize_disposable_postgres("/safe/bin", data_dir, tmp_path)

    message = str(error.value)
    assert "FATAL: shared memory unavailable" in message
    assert getpass.getuser() not in message
    assert str(tmp_path) not in message
    assert "<disposable-postgres-directory>" in message
