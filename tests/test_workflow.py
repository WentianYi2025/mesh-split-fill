import argparse
import base64
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import job
import storyboard
import install


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mesh-contract-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'job'
        self.root.mkdir()
        self.source = Path(self.temp.name) / 'shape.obj'
        self.source.write_text('v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n')
        self.data = job.initial(self.source, self.root)
        self.data.update({'inventory': {'complete': True, 'expected_count': 2, 'unresolved': []},
                          'parts': [{'id': p, 'name': p, 'evidence': 'explicit test fixture', 'preserve_openings': []} for p in ['a','b']],
                          'seams': [{'id': 's', 'parts': ['a','b'], 'action': 'complement', 'profile': 'planar', 'boundary_evidence': 'shared ring'}]})
        self.data['constraints']['axis_evidence'] = 'Z-up fixture'
        self.freeze()

    def freeze(self):
        job.write_json(self.root / 'job.json', self.data)
        self.key = hashlib.sha256(job.canonical(self.data)).hexdigest()
        job.write_json(self.root / 'freeze.json', {'contract_sha256': self.key})

    def test_source_change_invalidates_frozen_job(self):
        job.checked(self.root)
        self.source.write_text('different mesh')
        with self.assertRaisesRegex(ValueError, 'Source changed'):
            job.checked(self.root)

    def test_scope_change_requires_new_freeze(self):
        self.data['parts'][0]['preserve_openings'] = ['eyelet']
        job.write_json(self.root / 'job.json', self.data)
        with self.assertRaisesRegex(ValueError, 'Contract changed'):
            job.checked(self.root)

    def test_missing_inventory_and_invalid_complement_rejected(self):
        self.data['inventory']['expected_count'] = 3
        self.data['seams'][0]['parts'] = ['a']
        with self.assertRaises(ValueError):
            job.validate(self.data)

    def test_failed_candidate_budget_and_records_preserved(self):
        metrics = self.root / 'metrics.json'
        job.write_json(metrics, {'new_intersections': 1})
        args = argparse.Namespace(seam='s', strategy='projected', outcome='fail', seconds=1,
                                  metrics=metrics, script=self.source, artifact=[str(self.source)], note='bad seam')
        job.record(self.root, args)
        job.record(self.root, args)
        with self.assertRaisesRegex(ValueError, 'Two failures'):
            job.record(self.root, args)
        self.assertEqual(len(job.read_json(self.root / 'candidates.json')), 2)

    def test_story_requires_all_real_steps_and_matching_revision(self):
        self.data['storyboard'] = {'enabled': True, 'layout': 'comparison', 'output_format': 'html',
            'cases': [{'id': 'test', 'title': '<Actual geometry>', 'part_ids': ['a'], 'view': 'front', 'steps': ['Before', 'After']}]}
        self.freeze()
        evidence = self.root / 'evidence.json'
        job.write_json(evidence, {'contract_sha256': self.key, 'items': []})
        with self.assertRaisesRegex(ValueError, 'Missing real'):
            storyboard.build(self.root, evidence)
        png = self.root / 'tiny.png'
        png.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a2WQAAAAASUVORK5CYII='))
        items = [{'case_id': 'test', 'step': i, 'image': 'tiny.png', 'mesh': str(self.source), 'caption': '<verified>'} for i in [1,2]]
        job.write_json(evidence, {'contract_sha256': self.key, 'items': items})
        html = storyboard.build(self.root, evidence)
        self.assertIn('&lt;Actual geometry&gt;', html)
        self.assertIn('data:image/png;base64,', html)
        self.assertNotIn('<verified>', html)
        items[0]['mesh_sha256'] = '0'*64
        job.write_json(evidence, {'contract_sha256': self.key, 'items': items})
        with self.assertRaisesRegex(ValueError, 'Evidence changed'):
            storyboard.build(self.root, evidence)

    def test_install_is_scoped_and_replacement_keeps_backup(self):
        root = Path(self.temp.name) / '技能目录'
        result = install.install(root)
        marker = Path(result['path']) / 'keep-user-file.txt'
        marker.write_text('keep me')
        with self.assertRaises(ValueError):
            install.install(root)
        result = install.install(root, replace=True)
        self.assertEqual((Path(result['backup']) / marker.name).read_text(), 'keep me')
        self.assertTrue((Path(result['path']) / 'SKILL.md').is_file())


if __name__ == '__main__':
    unittest.main()
