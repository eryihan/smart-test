from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills' / 'smart-test' / 'scripts'
sys.path.insert(0, str(SCRIPTS))

from catalog import WORKFLOWS


class CatalogTests(unittest.TestCase):
    def test_command_files_cover_every_workflow_once(self):
        commands = {path.stem for path in (ROOT / 'commands').glob('*.md')}
        self.assertEqual(commands, set(WORKFLOWS))

    def test_command_files_have_descriptions(self):
        for workflow in WORKFLOWS:
            text = (ROOT / 'commands' / (workflow + '.md')).read_text()
            self.assertRegex(text, r'(?m)^description:\s*\S+')
