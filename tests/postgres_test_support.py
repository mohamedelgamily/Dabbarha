"""Helpers for disposable PostgreSQL integration-test services."""
import getpass
import re
import subprocess
from pathlib import Path

import pytest


def initialize_disposable_postgres(binary_dir: str, data_dir: Path, temporary_root: Path) -> None:
    """Run initdb and show safe diagnostics when an isolated cluster cannot start."""
    result = subprocess.run(
        [str(Path(binary_dir) / "initdb"), "-D", str(data_dir), "--no-locale",
         "--encoding=UTF8", "--auth=trust", "--username=dabbarha_test"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return

    output = result.stdout or "(initdb returned no diagnostic output)"
    output = output.replace(str(Path.home()), "$HOME")
    output = output.replace(str(temporary_root), "<disposable-postgres-directory>")
    username = getpass.getuser()
    if username:
        output = output.replace(username, "<local-user>")
    output = re.sub(r"(?<!\w)/(?:[^\s/:]+/){2,}[^\s:]*", "<path-redacted>", output)
    pytest.fail(f"Disposable PostgreSQL init failed (exit {result.returncode}):\n{output}")
