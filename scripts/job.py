"""Portable, source-bound mesh job contracts. Standard library only."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def canonical(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temp.replace(path)


def valid_id(value):
    return isinstance(value, str) and bool(re.fullmatch('[a-zA-Z0-9_-]+', value))


def validate(data):
    failures = []
    def require(condition, message):
        if not condition:
            failures.append(message)
    require(data.get('schema_version') == 1, 'schema_version must be 1')
    require(bool(data.get('job_id')), 'job_id required')
    source = data.get('source', {})
    require(bool(source.get('path')), 'source.path required')
    require(bool(re.fullmatch('[a-f0-9]{64}', source.get('sha256', ''))), 'source.sha256 required')
    parts = data.get('parts', [])
    ids = [p.get('id') for p in parts]
    require(bool(parts) and all(valid_id(i) for i in ids), 'enumerate all parts with simple IDs')
    require(len(ids) == len(set(ids)), 'duplicate part IDs')
    inv = data.get('inventory', {})
    require(inv.get('complete') is True, 'inventory.complete must be true after checking the entire model')
    require(inv.get('expected_count') == len(parts), 'expected_count must match parts')
    require(inv.get('unresolved') == [], 'resolve inventory.unresolved before freezing')
    for part in parts:
        require(bool(part.get('name')) and bool(part.get('evidence')), 'each part needs name and evidence')
        require(isinstance(part.get('preserve_openings'), list), 'each part needs preserve_openings (empty list allowed)')
    seams = data.get('seams', [])
    sids = [s.get('id') for s in seams]
    require(all(valid_id(s) for s in sids) and len(sids) == len(set(sids)), 'invalid/duplicate seam IDs')
    for seam in seams:
        owners = seam.get('parts', [])
        require(bool(owners) and all(o in ids for o in owners) and len(owners) == len(set(owners)), 'invalid seam owners')
        action, profile = seam.get('action'), seam.get('profile')
        require(action in ['leave_open', 'fill', 'complement'], 'invalid seam action')
        require(profile in ['none', 'planar', 'dome', 'strip', 'curvature'], 'invalid seam profile')
        require(bool(seam.get('boundary_evidence')), 'seam boundary_evidence required')
        require(action != 'complement' or len(owners) == 2, 'complement requires two distinct owners')
        require((action == 'leave_open') == (profile == 'none'), 'leave_open uses none; fill/complement need a profile')
    constraints = data.get('constraints', {})
    require(constraints.get('preserve_coordinates') is True, 'preserve_coordinates must be true')
    require(constraints.get('surface_policy') in ['preserve', 'local_transition'], 'invalid surface_policy')
    require(bool(constraints.get('axis_evidence')) and bool(constraints.get('units')), 'record axis evidence and units (unknown allowed)')
    tol = constraints.get('relative_tolerance')
    require(isinstance(tol, (int, float)) and not isinstance(tol, bool) and math.isfinite(tol) and 0 < tol < 0.1, 'relative_tolerance must be finite, positive and < 0.1')
    story = data.get('storyboard', {})
    require(isinstance(story.get('enabled'), bool), 'storyboard.enabled must be boolean')
    if story.get('enabled'):
        require(story.get('layout') in ['steps', 'comparison'], 'invalid storyboard layout')
        require(story.get('output_format') in ['html', 'png', 'pdf'], 'invalid storyboard output_format')
        cases = story.get('cases', [])
        cids = [c.get('id') for c in cases]
        require(bool(cases) and all(valid_id(c) for c in cids) and len(cids) == len(set(cids)), 'invalid/duplicate case IDs')
        for case in cases:
            require(bool(case.get('title')) and bool(case.get('view')), 'case needs title and view')
            require(bool(case.get('part_ids')) and all(p in ids for p in case['part_ids']), 'case refers to unknown parts')
            steps = case.get('steps', [])
            require(len(steps) >= 2 and all(isinstance(s, str) and s.strip() for s in steps), 'case needs at least two named steps')
    if failures:
        raise ValueError('; '.join(failures))


def checked(root, frozen=True):
    data = read_json(root / 'job.json')
    validate(data)
    source = Path(data['source']['path']).expanduser()
    if not source.is_absolute():
        source = root / source
    if digest(source) != data['source']['sha256']:
        raise ValueError('Source changed; inspect again before updating source.sha256')
    key = hashlib.sha256(canonical(data)).hexdigest()
    if frozen and read_json(root / 'freeze.json')['contract_sha256'] != key:
        raise ValueError('Contract changed; review affected outputs then freeze a new revision')
    return data, key


def initial(source, root):
    if (root / 'job.json').exists():
        raise ValueError('job.json already exists; refusing to overwrite')
    source = source.expanduser().resolve(strict=True)
    return {'schema_version': 1, 'job_id': root.name,
            'source': {'path': str(source), 'sha256': digest(source)},
            'inventory': {'complete': False, 'expected_count': None, 'unresolved': ['Inspect and enumerate the full intended parts list.']},
            'parts': [], 'seams': [],
            'constraints': {'preserve_coordinates': True, 'surface_policy': 'preserve', 'units': 'unknown', 'axis_evidence': '', 'relative_tolerance': 1e-6},
            'storyboard': {'enabled': False, 'layout': 'steps', 'output_format': 'html', 'cases': []}}


def record(root, args):
    data, key = checked(root)
    if args.seam not in {s['id'] for s in data['seams']}:
        raise ValueError('Unknown seam ID')
    path = root / 'candidates.json'
    history = read_json(path) if path.exists() else []
    previous = [r for r in history if r['contract_sha256'] == key and r['seam'] == args.seam and r['strategy'] == args.strategy]
    if sum(r['outcome'] == 'fail' for r in previous) >= 2:
        raise ValueError('Two failures: diagnose and choose a meaningfully different strategy')
    if not math.isfinite(args.seconds) or args.seconds < 0:
        raise ValueError('seconds must be finite and nonnegative')
    metrics = read_json(args.metrics)
    if not isinstance(metrics, dict) or not metrics:
        raise ValueError('metrics must be a nonempty JSON object')
    item = {'contract_sha256': key, 'seam': args.seam, 'strategy': args.strategy, 'outcome': args.outcome,
            'timestamp': datetime.now(timezone.utc).isoformat(), 'seconds': args.seconds, 'metrics': metrics,
            'script_sha256': digest(args.script), 'note': args.note,
            'artifacts': [{'path': str(Path(p).resolve(strict=True)), 'sha256': digest(p)} for p in args.artifact]}
    history.append(item)
    write_json(path, history)
    return item


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ['init', 'validate', 'freeze', 'check', 'record', 'cache-key']:
        p = sub.add_parser(name)
        p.add_argument('--job-dir', required=True, type=Path)
        if name == 'init':
            p.add_argument('--input', required=True, type=Path)
        if name == 'cache-key':
            p.add_argument('--file', action='append', required=True, help='Every mesh, script and adapter dependency; order significant')
            p.add_argument('--parameters', required=True, type=Path)
            p.add_argument('--runtime', required=True, help='Blender/Python/library versions and platform')
        if name == 'record':
            for field in ['seam', 'strategy', 'note']:
                p.add_argument('--' + field, required=True)
            p.add_argument('--outcome', choices=['pass', 'fail', 'incomplete'], required=True)
            p.add_argument('--seconds', type=float, required=True)
            p.add_argument('--metrics', type=Path, required=True)
            p.add_argument('--script', type=Path, required=True)
            p.add_argument('--artifact', action='append', default=[])
    args = parser.parse_args()
    root = args.job_dir.expanduser().resolve()
    try:
        if args.command == 'init':
            write_json(root / 'job.json', initial(args.input, root))
            result = {'status': 'draft', 'job': str(root / 'job.json')}
        elif args.command == 'record':
            result = record(root, args)
        else:
            data, key = checked(root, args.command in ['check', 'cache-key'])
            result = {'contract_sha256': key}
            if args.command == 'freeze':
                write_json(root / 'contracts' / (key + '.json'), data)
                write_json(root / 'freeze.json', result)
            elif args.command == 'cache-key':
                payload = {'contract': key, 'files': [digest(p) for p in args.file], 'parameters': read_json(args.parameters), 'runtime': args.runtime}
                result['cache_key'] = hashlib.sha256(canonical(payload)).hexdigest()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
