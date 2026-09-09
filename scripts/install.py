"""Install only this skill; explicit replacement retains a timestamped backup."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import sys
import uuid


def install(skills_dir, replace=False):
    source = Path(__file__).resolve().parents[1]
    root = Path(skills_dir).expanduser().resolve()
    target = root / 'mesh-split-fill'
    if target.resolve() == source:
        return {'status': 'already_installed', 'path': str(target)}
    if target.is_symlink():
        raise ValueError('Refusing to replace a symlink destination')
    if source in target.parents or target in source.parents:
        raise ValueError('Source and destination cannot contain one another')
    if target.exists() and not replace:
        raise ValueError('Skill already exists; use --replace to retain it as a backup and install this version')
    if target.exists() and not target.is_dir():
        raise ValueError('Destination exists and is not a directory')
    for path in source.rglob('*'):
        if path.is_symlink():
            raise ValueError('Distribution contains a symlink: ' + str(path))
    root.mkdir(parents=True, exist_ok=True)
    stage = root / ('.mesh-split-fill-install-' + uuid.uuid4().hex[:10])
    shutil.copytree(source, stage, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.DS_Store'))
    backup = None
    if target.exists():
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        backups = root.parent / 'skill-backups'
        backups.mkdir(parents=True, exist_ok=True)
        backup = backups / ('mesh-split-fill-' + stamp + '-' + uuid.uuid4().hex[:6])
        target.rename(backup)
    try:
        stage.rename(target)
    except OSError:
        if backup is not None and not target.exists():
            backup.rename(target)
        raise
    return {'status': 'installed', 'path': str(target), 'backup': str(backup) if backup else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    default_root = Path(os.environ['CODEX_HOME']).expanduser() if os.environ.get('CODEX_HOME') else Path.home() / '.codex'
    parser.add_argument('--skills-dir', type=Path, default=default_root / 'skills')
    parser.add_argument('--replace', action='store_true')
    args = parser.parse_args()
    try:
        import json
        print(json.dumps(install(args.skills_dir, args.replace), ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
