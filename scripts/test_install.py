"""Installation invariants in isolated directories; never touches real user skills."""
import tempfile
import unittest
from pathlib import Path
from install import destination, install

SOURCE = Path(__file__).resolve().parents[1]


class InstallTests(unittest.TestCase):
    def test_both_project_layouts_preserve_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            for platform, config in [('claude', '.claude'), ('codex', '.agents')]:
                target = destination(platform, project=folder)
                self.assertEqual(target, Path(folder) / config / 'skills/consilium')
                install(SOURCE, target)
                for root in ('agents', 'assets', 'references', 'scripts'):
                    for item in (SOURCE / root).rglob('*'):
                        if item.is_file() and '__pycache__' not in item.parts:
                            self.assertEqual(item.read_bytes(), (target / item.relative_to(SOURCE)).read_bytes())
                self.assertEqual((target/'SKILL.md').read_bytes(), (SOURCE/'SKILL.md').read_bytes())
                self.assertFalse((target/'.git').exists())

    def test_existing_install_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/'existing'
            target.mkdir()
            (target/'user-file').write_text('keep')
            with self.assertRaises(ValueError):
                install(SOURCE, target)
            self.assertEqual((target/'user-file').read_text(), 'keep')

    def test_recursive_destination_is_refused(self):
        with self.assertRaises(ValueError):
            install(SOURCE, SOURCE/'recursive-install-test')

    def test_user_paths_can_be_resolved_without_changing_home(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(destination('claude', user_home=folder), Path(folder)/'.claude/skills/consilium')
            self.assertEqual(destination('codex', user_home=folder), Path(folder)/'.agents/skills/consilium')

    def test_symlinked_destination_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/'link'
            target.symlink_to(Path(folder)/'missing', target_is_directory=True)
            with self.assertRaises(ValueError):
                install(SOURCE, target)


if __name__ == '__main__':
    unittest.main(verbosity=2)
