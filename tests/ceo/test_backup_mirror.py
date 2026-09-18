"""«Зеркало» in the backup: encrypted archive, never in the plain part."""
import importlib.util
import os
import shutil
import sqlite3
import subprocess
import tarfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "skills" / "ceo" / "backup" / "scripts" / "backup.py"

pytestmark = pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl not installed")


def _load(monkeypatch, home: Path, key: str | None):
    monkeypatch.setenv("HERMES_HOME", str(home))
    if key is None:
        monkeypatch.delenv("BACKUP_MIRROR_KEY", raising=False)
    else:
        monkeypatch.setenv("BACKUP_MIRROR_KEY", key)
    spec = importlib.util.spec_from_file_location("ceo_backup", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _db(path: Path, rows: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE t (v TEXT)")
    con.executemany("INSERT INTO t VALUES (?)", [(f"row{i}",) for i in range(rows)])
    con.commit()
    con.close()


@pytest.fixture
def home(tmp_path: Path) -> Path:
    h = tmp_path / "home"
    (h / "profiles" / "mirror" / "memories").mkdir(parents=True)
    (h / "profiles" / "mirror" / "memories" / "MEMORY.md").write_text("узор: сверхответственность", encoding="utf-8")
    _db(h / "profiles" / "mirror" / "state.db", 3)
    _db(h / "kanban" / "boards" / "mirror" / "kanban.db", 2)
    _db(h / "kanban" / "boards" / "lichnoe" / "kanban.db", 1)
    (h / "kanban" / "boards" / "mirror" / "board.json").write_text("{}", encoding="utf-8")
    return h


def test_mirror_archive_roundtrip_and_plain_part_is_clean(monkeypatch, home, tmp_path):
    mod = _load(monkeypatch, home, "test-passphrase")
    staging = tmp_path / "staging"

    assert mod.backup_mirror(staging) is None
    enc = staging / "state" / "mirror.tar.enc"
    assert enc.is_file() and (staging / "state" / "mirror.tar.enc.sha256").is_file()
    assert "сверхответственность" not in enc.read_bytes().decode("latin-1")

    # Plain part: other boards yes, the closed board no.
    mod.backup_kanban(staging)
    mod.copy_includes(staging)
    assert (staging / "state" / "kanban" / "lichnoe.db.gz").is_file()
    assert not (staging / "state" / "kanban" / "mirror.db.gz").exists()
    assert not (staging / "kanban" / "boards" / "mirror").exists()

    # Decrypts back to memory + both databases.
    out = tmp_path / "restored"
    out.mkdir()
    plain = subprocess.run(
        ["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", mod.MIRROR_KDF_ITER,
         "-pass", "env:BACKUP_MIRROR_KEY", "-in", str(enc)],
        capture_output=True, check=True, env={**os.environ, "BACKUP_MIRROR_KEY": "test-passphrase"},
    ).stdout
    tar_path = out / "mirror.tar"
    tar_path.write_bytes(plain)
    with tarfile.open(tar_path) as tar:
        names = set(tar.getnames())
    assert names == {"memories/MEMORY.md", "state.db.gz", "kanban.db.gz"}


def test_unchanged_mirror_keeps_previous_ciphertext(monkeypatch, home, tmp_path):
    mod = _load(monkeypatch, home, "test-passphrase")
    staging = tmp_path / "staging"
    mod.backup_mirror(staging)
    first = (staging / "state" / "mirror.tar.enc").read_bytes()
    mod.backup_mirror(staging)
    assert (staging / "state" / "mirror.tar.enc").read_bytes() == first

    (home / "profiles" / "mirror" / "memories" / "MEMORY.md").write_text("новая запись", encoding="utf-8")
    mod.backup_mirror(staging)
    assert (staging / "state" / "mirror.tar.enc").read_bytes() != first


def test_without_key_owner_gets_one_russian_line(monkeypatch, home, tmp_path):
    mod = _load(monkeypatch, home, None)
    staging = tmp_path / "staging"
    notice = mod.backup_mirror(staging)
    assert notice == "🪞 Зеркало не попало в копию: не задан ключ шифрования."
    assert not (staging / "state" / "mirror.tar.enc").exists()


def test_no_mirror_data_is_silent(monkeypatch, tmp_path):
    mod = _load(monkeypatch, tmp_path / "empty", None)
    assert mod.backup_mirror(tmp_path / "staging") is None
