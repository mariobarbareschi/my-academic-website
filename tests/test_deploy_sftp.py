"""Offline guardrail tests. No remote connection is made."""

import importlib.util
import stat
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

PATH = Path(__file__).resolve().parents[1] / "scripts" / "deploy_sftp.py"
spec = importlib.util.spec_from_file_location("deploy_sftp", PATH)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class TestDeploymentSafety(unittest.TestCase):
    def test_production_root_allowed(self):
        self.assertEqual(mod.get_target("/home/mario.barbareschi/"), mod.ALLOWED_ROOT)

    def test_preview_allowed(self):
        self.assertEqual(mod.get_target("/home/mario.barbareschi/_academic-preview/"), mod.DEFAULT_TARGET.rstrip("/"))

    def test_rejects_outside_home(self):
        for path in ("/home/another_user", "/etc", "/home/mario.barbareschi-backup"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                mod.get_target(path)

    def test_rejects_traversal(self):
        for path in ("/home/mario.barbareschi/../another", "/home/mario.barbareschi/./t"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                mod.get_target(path)

    def test_rejects_protected_folders(self):
        for path in ("/home/mario.barbareschi/old_but_gold", "/home/mario.barbareschi/.cache/p"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                mod.get_target(path)

    def test_upload_only_public_site_files(self):
        files = mod.local_files()
        self.assertTrue(any(rel == "index.html" for _, rel in files))
        self.assertTrue(any(rel == "data/publications.json" for _, rel in files))
        self.assertFalse(any("/." in "/" + rel or rel.startswith(".") for _, rel in files))

    def test_dry_run_does_not_create_directories(self):
        sftp = MagicMock()
        sftp.lstat.side_effect = OSError("not found")
        mod.check_ancestors(sftp, "/home/mario.barbareschi/_academic-preview", create=False)
        sftp.mkdir.assert_not_called()

    def test_symlink_directory_is_rejected(self):
        sftp = MagicMock()
        sftp.lstat.return_value.st_mode = stat.S_IFLNK | 0o777
        with self.assertRaises(RuntimeError):
            mod.check_ancestors(sftp, "/home/mario.barbareschi/_academic-preview", create=True)

    def test_symlink_file_is_rejected(self):
        sftp = MagicMock()
        sftp.lstat.return_value.st_mode = stat.S_IFLNK | 0o777
        with self.assertRaises(RuntimeError):
            mod.verify_existing_file(sftp, "/home/mario.barbareschi/index.html")


if __name__ == "__main__":
    unittest.main()
