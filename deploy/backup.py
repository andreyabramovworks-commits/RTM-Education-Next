"""Backup and restore-check RTM Education Next data with an isolated Compose project."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import tarfile
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ROOT / "compose.yaml"
PROJECT_RE = re.compile(r"^[a-z][a-z0-9_-]{2,60}$")


def command(*args: str, stdin=None, stdout=None) -> None:
    subprocess.run(args, check=True, stdin=stdin, stdout=stdout)


def compose(project: str, *args: str, stdin=None, stdout=None) -> None:
    command("docker", "compose", "-p", project, "-f", str(COMPOSE), *args, stdin=stdin, stdout=stdout)


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def create(project: str, backup_root: Path) -> Path:
    backup_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    backup_root.chmod(0o700)
    target = backup_root / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
    target.mkdir(mode=0o700)
    dump = target / "database.dump"
    with dump.open("xb") as output:
        compose(project, "exec", "-T", "db", "pg_dump", "-U", "rtm_next", "-d", "rtm_education_next", "-Fc", stdout=output)
    dump.chmod(0o600)
    command("docker", "run", "--rm", "--network", "none",
            "-v", f"{project}_next_media:/media:ro", "-v", f"{target}:/backup",
            "postgres:17-alpine", "sh", "-c", "tar -C /media -czf /backup/media.tar.gz . && " +
            f"chown {os.getuid()}:{os.getgid()} /backup/media.tar.gz")
    (target / "media.tar.gz").chmod(0o600)
    data = ROOT / "data"
    data.mkdir(mode=0o700, exist_ok=True)
    command("docker", "run", "--rm", "--network", "none",
            "-v", f"{data}:/runtime:ro", "-v", f"{target}:/backup",
            "postgres:17-alpine", "sh", "-c", "tar -C /runtime -czf /backup/runtime.tar.gz . && " +
            f"chown {os.getuid()}:{os.getgid()} /backup/runtime.tar.gz")
    (target / "runtime.tar.gz").chmod(0o600)
    manifest = {"project": project, "created_at": datetime.now(timezone.utc).isoformat(),
                "files": {name: digest(target / name) for name in ("database.dump", "media.tar.gz", "runtime.tar.gz")}}
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (target / "manifest.json").chmod(0o600)
    return target


def verify(project: str, target: Path) -> None:
    target = target.resolve(strict=True)
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("project") != project:
        raise ValueError("Backup belongs to another Compose project")
    for name, expected in manifest["files"].items():
        if digest(target / name) != expected:
            raise ValueError(f"Backup checksum mismatch: {name}")
    restore_db = "rtm_next_restore_" + uuid.uuid4().hex[:10]
    compose(project, "exec", "-T", "db", "createdb", "-U", "rtm_next", restore_db)
    try:
        with (target / "database.dump").open("rb") as source:
            compose(project, "exec", "-T", "db", "pg_restore", "-U", "rtm_next",
                    "--no-owner", "--no-privileges", "-d", restore_db, stdin=source)
        compose(project, "exec", "-T", "db", "psql", "-U", "rtm_next", "-d", restore_db,
                "-At", "-c", "SELECT version_num FROM public.alembic_version")
    finally:
        compose(project, "exec", "-T", "db", "dropdb", "-U", "rtm_next", "--if-exists", restore_db)
    with tempfile.TemporaryDirectory(prefix="rtm-media-restore-", dir=target.parent) as directory:
        command("docker", "run", "--rm", "--network", "none", "-v", f"{target}:/backup:ro",
                "-v", f"{directory}:/restore", "postgres:17-alpine", "sh", "-c",
                "tar -C /restore -xzf /backup/media.tar.gz && " +
                f"chown -R {os.getuid()}:{os.getgid()} /restore")
    with tarfile.open(target / "runtime.tar.gz", "r:gz") as archive:
        for item in archive:
            normalized = item.name.removeprefix("./")
            if item.isdir() and normalized in ("", "."):
                continue
            if not item.isfile() or not normalized or Path(normalized).name != normalized:
                raise ValueError("Unexpected runtime backup entry")
            stream = archive.extractfile(item)
            if stream is not None:
                while stream.read(1024 * 1024):
                    pass
    print(f"Backup restore verified: {target}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["create", "verify"])
    parser.add_argument("--project", default="rtm-education-next")
    parser.add_argument("--backup-root", type=Path, default=ROOT / "backups")
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()
    if not PROJECT_RE.fullmatch(args.project):
        parser.error("Invalid project name")
    os.umask(0o077)
    if args.action == "create":
        print(create(args.project, args.backup_root.resolve()))
    else:
        if args.backup is None:
            parser.error("--backup is required for verify")
        verify(args.project, args.backup)


if __name__ == "__main__":
    main()
