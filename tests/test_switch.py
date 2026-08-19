import os
import tempfile
import unittest

from free_models_monitor import switch


class SwitchTests(unittest.TestCase):
    def test_dry_run_does_not_modify_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.json")
            original = '{"model": "openrouter/old:free"}'
            with open(path, "w") as f:
                f.write(original)
            code = switch.main(
                [
                    "--from",
                    "openrouter/old:free",
                    "--to",
                    "openrouter/new:free",
                    "--file",
                    path,
                    "--dry-run",
                ]
            )
            self.assertEqual(code, 0)
            with open(path) as f:
                self.assertEqual(f.read(), original)
            self.assertFalse(
                any(f.startswith("config.json.bak-") for f in os.listdir(tmp))
            )

    def test_default_without_apply_does_not_modify_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.json")
            original = '{"model": "openrouter/old:free"}'
            with open(path, "w") as f:
                f.write(original)
            code = switch.main(
                [
                    "--from",
                    "openrouter/old:free",
                    "--to",
                    "openrouter/new:free",
                    "--file",
                    path,
                ]
            )
            self.assertEqual(code, 0)
            with open(path) as f:
                self.assertEqual(f.read(), original)

    def test_apply_replaces_and_creates_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.json")
            with open(path, "w") as f:
                f.write('{"model": "openrouter/old:free"}')
            code = switch.main(
                [
                    "--from",
                    "openrouter/old:free",
                    "--to",
                    "openrouter/new:free",
                    "--file",
                    path,
                    "--apply",
                ]
            )
            self.assertEqual(code, 0)
            with open(path) as f:
                content = f.read()
            self.assertIn("openrouter/new:free", content)
            self.assertNotIn("openrouter/old:free", content)
            backups = [f for f in os.listdir(tmp) if f.startswith("config.json.bak-")]
            self.assertEqual(len(backups), 1)

    def test_missing_file_returns_error(self):
        code = switch.main(
            ["--from", "a", "--to", "b", "--file", "/nonexistent/path.json", "--apply"]
        )
        self.assertEqual(code, 1)

    def test_no_occurrence_leaves_file_untouched_and_no_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.json")
            with open(path, "w") as f:
                f.write('{"model": "something-else"}')
            code = switch.main(
                [
                    "--from",
                    "openrouter/old:free",
                    "--to",
                    "openrouter/new:free",
                    "--file",
                    path,
                    "--apply",
                ]
            )
            self.assertEqual(code, 0)
            backups = [f for f in os.listdir(tmp) if f.startswith("config.json.bak-")]
            self.assertEqual(len(backups), 0)

    def test_multiple_files_all_get_backed_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            path1 = os.path.join(tmp, "a.json")
            path2 = os.path.join(tmp, "b.json")
            with open(path1, "w") as f:
                f.write("openrouter/old:free")
            with open(path2, "w") as f:
                f.write("openrouter/old:free")
            code = switch.main(
                [
                    "--from",
                    "openrouter/old:free",
                    "--to",
                    "openrouter/new:free",
                    "--file",
                    path1,
                    "--file",
                    path2,
                    "--apply",
                ]
            )
            self.assertEqual(code, 0)
            with open(path1) as f:
                self.assertIn("openrouter/new:free", f.read())
            with open(path2) as f:
                self.assertIn("openrouter/new:free", f.read())


if __name__ == "__main__":
    unittest.main()
