"""Focused CLI checks using existing Git objects; no repository writes."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/verify_technical_evidence_index.py'


def git(*args):
    return subprocess.check_output(['git', '-c', f'safe.directory={ROOT.as_posix()}', '-C', str(ROOT), *args])


class EvidenceIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.commit = git('rev-parse', 'HEAD').decode().strip()
        cls.digest = hashlib.sha256(git('show', f'{cls.commit}:README.md')).hexdigest()

    def entry(self, **extra):
        return dict(path='README.md', sha256=self.digest, **extra)

    def run_index(self, entries, *args):
        with tempfile.TemporaryDirectory() as directory:
            index = Path(directory) / 'index.json'
            index.write_text(json.dumps({'linked_documents': entries}), encoding='utf-8')
            result = subprocess.run([sys.executable, '-B', str(SCRIPT), str(index), *args], capture_output=True, text=True)
        return result.returncode, result.stdout + result.stderr

    def test_duplicates_are_counted_and_verified(self):
        code, output = self.run_index([self.entry(), self.entry()])
        self.assertEqual(code, 0, output)
        self.assertIn('1 distinct documents / 2 references', output)

    def test_explicit_commit_overrides_default_and_history_is_metadata(self):
        entry = self.entry(sha256_basis=f'Committed Git blob bytes at {self.commit}; corrected 2026-10-04.',
                           historical_working_tree_sha256='0' * 64)
        code, output = self.run_index([entry], '--commit', 'main')
        self.assertEqual(code, 0, output)
        self.assertIn(self.commit, output)

    def test_mismatch_reports_path_and_expected_actual(self):
        entry = self.entry()
        entry['sha256'] = '0' * 64
        code, output = self.run_index([entry])
        self.assertEqual(code, 1, output)
        for text in ['README.md', 'expected', 'actual', self.digest]:
            self.assertIn(text, output)

    def test_missing_document_reports_path(self):
        entry = self.entry()
        entry['path'] = 'docs/no-such-evidence-document-for-verifier-test.md'
        code, output = self.run_index([entry])
        self.assertEqual(code, 1, output)
        self.assertIn(entry['path'], output)
        self.assertIn('missing', output)

    def test_conflicting_duplicate_is_failure(self):
        other = self.entry()
        other['sha256'] = '0' * 64
        code, output = self.run_index([self.entry(), other])
        self.assertEqual(code, 1, output)
        self.assertIn('conflicting duplicate', output)

    def test_unknown_basis_is_not_silently_ignored(self):
        code, output = self.run_index([self.entry(sha256_basis='working bytes')])
        self.assertEqual(code, 1, output)
        self.assertIn('unsupported sha256_basis', output)


if __name__ == '__main__':
    unittest.main()
