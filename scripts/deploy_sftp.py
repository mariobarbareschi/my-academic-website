#!/usr/bin/env python3
"""Deploy the static site to Unina over pinned-host-key SFTP.

Safe properties:
- never falls back to unencrypted FTP or permissive SSH host key checks;
- refuses destinations outside the user's home directory or protected folders;
- uploads only non-hidden regular files under site/, without remote deletion;
- dry-run by default and never creates remote files/directories in dry-run mode.
"""

from __future__ import annotations

import os
import posixpath
import stat
import sys
import tempfile
from pathlib import Path

HOST = "wpage.unina.it"
PORT = 22
USERNAME = "mario.barbareschi"
ALLOWED_ROOT = "/home/mario.barbareschi"
PROTECTED_DIRECTORIES = {"old_but_gold", ".cache"}
SITE_DIR = Path(__file__).resolve().parents[1] / "site"
DEFAULT_TARGET = ALLOWED_ROOT + "/_academic-preview/"


def get_target(raw: str) -> str:
    if not raw or not raw.startswith("/"):
        raise ValueError("SFTP_REMOTE_DIR must be an absolute path")
    if any(part in {".", ".."} for part in raw.split("/")):
        raise ValueError("SFTP_REMOTE_DIR must not include . or .. segments")
    target = posixpath.normpath(raw)
    if posixpath.commonpath([ALLOWED_ROOT, target]) != ALLOWED_ROOT:
        raise ValueError("Destination is outside /home/mario.barbareschi")
    relative_parts = target.removeprefix(ALLOWED_ROOT).strip("/").split("/")
    if PROTECTED_DIRECTORIES.intersection(relative_parts):
        raise ValueError("Destination overlaps a protected remote directory")
    return target


def local_files() -> list[tuple[Path, str]]:
    if not SITE_DIR.is_dir():
        raise FileNotFoundError(f"Website directory missing: {SITE_DIR}")
    result = []
    for path in sorted(SITE_DIR.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(SITE_DIR)
        if any(part.startswith(".") for part in relative.parts):
            continue
        result.append((path, relative.as_posix()))
    if not result or not any(rel == "index.html" for _, rel in result):
        raise RuntimeError("Refusing deployment: site/index.html not found")
    return result


def check_ancestors(sftp, destination: str, *, create: bool) -> None:
    """Reject symlinks along destination paths, creating missing directories if allowed."""
    components = destination.lstrip("/").split("/")
    current = "/"
    for component in components:
        current = posixpath.join(current, component)
        try:
            info = sftp.lstat(current)
        except OSError:
            if not create:
                print(f"Dry run: remote directory {current} does not exist yet (would create).")
                return
            sftp.mkdir(current)
            info = sftp.lstat(current)
        if not stat.S_ISDIR(info.st_mode):
            raise RuntimeError(f"Unsafe destination: {current} is not a real directory")


def verify_existing_file(sftp, path: str) -> None:
    try:
        info = sftp.lstat(path)
    except OSError:
        return  # File will be created, never deleted.
    if not stat.S_ISREG(info.st_mode):
        raise RuntimeError(f"Refusing to overwrite non-regular file: {path}")


def make_client(known_hosts_text: str, password: str):
    import paramiko  # only needed by deployments; installed by workflow

    if not known_hosts_text.strip():
        raise ValueError("Missing SFTP_KNOWN_HOSTS; refusing unverified SSH connection")
    if not password:
        raise ValueError("Missing SFTP_PASSWORD")
    path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as f:
            os.chmod(f.name, 0o600)
            f.write(known_hosts_text)
            if not known_hosts_text.endswith("\n"):
                f.write("\n")
            path = f.name
        client = paramiko.SSHClient()
        client.load_host_keys(path)
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        # Fail fast if the supplied known_hosts lacks this exact host.
        if not client.get_host_keys().lookup(HOST):
            raise ValueError(f"SFTP_KNOWN_HOSTS lacks a key for {HOST}")
        return client
    finally:
        if path:
            os.unlink(path)


def deploy() -> None:
    dest = get_target(os.getenv("SFTP_REMOTE_DIR", DEFAULT_TARGET))
    dry_run = os.getenv("DEPLOY_DRY_RUN", "true").strip().lower() != "false"
    files = local_files()
    password = os.getenv("SFTP_PASSWORD", "")
    known_hosts = os.getenv("SFTP_KNOWN_HOSTS", "")
    client = make_client(known_hosts, password)

    print(f"Connecting to {HOST}:{PORT} as {USERNAME}; strict SSH host-key verification ON")
    print(f"Target directory: {dest}/")
    print(f"Files under site/: {len(files)}; dry run: {dry_run}")
    try:
        client.connect(
            hostname=HOST,
            port=PORT,
            username=USERNAME,
            password=password,
            look_for_keys=False,
            allow_agent=False,
            timeout=20,
            auth_timeout=20,
            banner_timeout=20,
        )
        with client.open_sftp() as sftp:
            check_ancestors(sftp, ALLOWED_ROOT, create=False)
            check_ancestors(sftp, dest, create=not dry_run)
            if dry_run:
                print(f"DRY RUN OK: authenticated; host key verified; would upload {len(files)} files.")
                print("No remote files or directories were created, changed or deleted.")
                return
            uploaded = 0
            for source, relative in files:
                remote_path = posixpath.join(dest, relative)
                remote_parent = posixpath.dirname(remote_path)
                check_ancestors(sftp, remote_parent, create=True)
                verify_existing_file(sftp, remote_path)
                sftp.put(str(source), remote_path, confirm=True)
                uploaded += 1
            print(f"SFTP DEPLOY OK: uploaded {uploaded} files to {dest}/")
            print("No remote files were deleted. old_but_gold and .cache were not touched.")
    finally:
        client.close()


if __name__ == "__main__":
    try:
        deploy()
    except Exception as exc:
        print(f"SFTP deployment failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
