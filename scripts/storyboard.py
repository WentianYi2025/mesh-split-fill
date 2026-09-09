"""Build a self-contained process page from a frozen plan and real local evidence."""
import argparse
import base64
from html import escape
import json
from pathlib import Path
import sys

from job import checked, digest, read_json


def asset(root, value):
    path = Path(value).expanduser()
    return (root / path).resolve(strict=True) if not path.is_absolute() else path.resolve(strict=True)


def image_uri(path):
    data = path.read_bytes()
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        mime = 'image/png'
    elif data.startswith(b'\xff\xd8\xff'):
        mime = 'image/jpeg'
    else:
        raise ValueError('Evidence image must be an actual PNG or JPEG: ' + str(path))
    return 'data:' + mime + ';base64,' + base64.b64encode(data).decode('ascii')


def build(root, evidence_file):
    job, key = checked(root)
    story = job['storyboard']
    if not story['enabled']:
        raise ValueError('Storyboard is disabled in the frozen contract')
    evidence = read_json(evidence_file)
    if evidence.get('contract_sha256') != key:
        raise ValueError('Evidence belongs to a different contract revision')
    expected = {(c['id'], i + 1) for c in story['cases'] for i in range(len(c['steps']))}
    mapping = {}
    for row in evidence.get('items', []):
        identity = (row['case_id'], row['step'])
        if identity not in expected or identity in mapping:
            raise ValueError('Unknown or duplicate evidence case/step: ' + str(identity))
        if not row.get('caption'):
            raise ValueError('Each step needs an evidence-grounded caption')
        mapping[identity] = row
    if set(mapping) != expected:
        raise ValueError('Missing real intermediate evidence: ' + str(sorted(expected - set(mapping))))
    sections, sources = [], []
    for case in story['cases']:
        cards = []
        for i, title in enumerate(case['steps'], 1):
            row = mapping[(case['id'], i)]
            img, mesh = asset(root, row['image']), asset(root, row['mesh'])
            source = {'case_id': case['id'], 'step': i, 'image': str(img), 'image_sha256': digest(img),
                      'mesh': str(mesh), 'mesh_sha256': digest(mesh), 'caption': row['caption']}
            for field in ['image_sha256', 'mesh_sha256']:
                if field in row and row[field] != source[field]:
                    raise ValueError('Evidence changed: ' + field)
            sources.append(source)
            cards.append('<figure><img alt="' + escape(title, quote=True) + '" src="' + image_uri(img) + '"><figcaption><b>'
                         + escape(f'{i:02d} · {title}') + '</b><p>' + escape(row['caption']) + '</p></figcaption></figure>')
        sections.append('<section><h2>' + escape(case['title']) + '</h2><p class="view">' + escape(case['view'])
                        + '</p><div class="cards">' + ''.join(cards) + '</div></section>')
    columns = 2 if story['layout'] == 'comparison' else 3
    css = """*{box-sizing:border-box}body{margin:0;background:#eef1f4;color:#18232d;font-family:system-ui,-apple-system,'Segoe UI','Microsoft YaHei','PingFang SC',sans-serif}main{max-width:1440px;margin:auto;padding:42px}h1{font-size:32px;margin:0 0 12px}h2{font-size:24px}.meta,.view{color:#506375;font-size:14px}.cards{display:grid;gap:18px;grid-template-columns:repeat(COLS,minmax(0,1fr))}section{margin:38px 0}figure{background:white;border:1px solid #d4dce3;border-radius:8px;margin:0;overflow:hidden;break-inside:avoid}img{display:block;width:100%;height:auto;background:#fafbfc}figcaption{padding:18px;overflow-wrap:anywhere}figcaption b{font-size:17px}p{line-height:1.6}details{margin-top:35px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px}@media(max-width:800px){main{padding:20px}.cards{grid-template-columns:1fr}}@media print{body{background:white}main{padding:0}section{break-before:page}section:first-of-type{break-before:auto}details{display:none}figure{break-inside:avoid}}""".replace('COLS', str(columns))
    heading = story.get('title') or '三维拆件与补洞 · 实际过程'
    html = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + escape(heading) + '</title><style>' + css + '</style><main><h1>' + escape(heading) + '</h1><p class="meta">'
    html += escape(job['job_id'] + ' · 真实项目网格与渲染 · 契约 ' + key[:12]) + '</p>' + ''.join(sections)
    html += '<details><summary>来源与校验</summary><pre>' + escape(json.dumps({'contract_sha256': key, 'sources': sources}, ensure_ascii=False, indent=2)) + '</pre></details></main></html>'
    return html


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job-dir', required=True, type=Path)
    parser.add_argument('--evidence', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.output.suffix.lower() != '.html':
            raise ValueError('This helper creates HTML; use a separate verified renderer for PNG/PDF')
        content = build(args.job_dir.resolve(), args.evidence)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(content)
        print(str(args.output.resolve()))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
