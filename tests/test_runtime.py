import importlib.util
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "scripts" / "runtime.py"
spec = importlib.util.spec_from_file_location("runtime", RUNTIME)
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class RuntimeTests(unittest.TestCase):
    def test_macos_candidates_include_system_and_user_applications(self):
        with mock.patch.object(runtime, "os") as os_mock, mock.patch.object(runtime.sys, "platform", "darwin"):
            os_mock.name = "posix"
            paths = list(runtime.blender_candidates())
        rendered = [str(path) for path in paths]
        self.assertTrue(any("Applications" in path and "Blender.app" in path for path in rendered))

    def test_windows_candidates_include_steam_location(self):
        with mock.patch.object(runtime, "os") as os_mock, mock.patch.object(runtime.sys, "platform", "win32"):
            os_mock.name = "nt"
            os_mock.environ = {"ProgramFiles(x86)": r"C:\Program Files (x86)"}
            paths = list(runtime.blender_candidates())
        expected = Path(r"C:\Program Files (x86)") / "Steam" / "steamapps" / "common" / "Blender" / "blender.exe"
        self.assertIn(expected, paths)

    def test_thread_count_is_positive_and_capped(self):
        with mock.patch.object(runtime.os, "cpu_count", return_value=4):
            self.assertEqual(runtime.available_threads(None), 4)
            self.assertEqual(runtime.available_threads(99), 4)
            with self.assertRaises(ValueError):
                runtime.available_threads(0)

    def test_default_threads_preserves_small_machine_capacity(self):
        with mock.patch.object(runtime.os, "cpu_count", return_value=2):
            self.assertEqual(runtime.available_threads(None), 2)

    def test_missing_script_is_nonzero(self):
        result = subprocess.run([sys.executable, str(RUNTIME), "run", "--blender", sys.executable,
                                 "--log", str(Path(tempfile.gettempdir()) / "blender runtime.log"), "missing.py"],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)

    def test_unicode_log_path_and_no_shell_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "含 空格"
            folder.mkdir()
            script = folder / "tool.py"
            script.write_text("pass", encoding="utf-8")
            log = folder / "运行.log"
            fake = folder / "fake blender.py"
            fake.write_text("", encoding="utf-8")
            with mock.patch.object(runtime, "require_supported_blender", return_value=fake), \
                 mock.patch.object(runtime.subprocess, "run", return_value=mock.Mock(returncode=0)) as run:
                code = runtime.main(["run", "--log", str(log), str(script), "--value", "a b"])
            self.assertEqual(code, 0)
            self.assertTrue(log.exists())
            self.assertFalse(run.call_args.kwargs["shell"])
            self.assertIn("a b", run.call_args.args[0])

    def test_log_cannot_overwrite_script(self):
        with tempfile.TemporaryDirectory() as temp:
            script = Path(temp) / "tool.py"
            script.write_text("pass", encoding="utf-8")
            with mock.patch.object(runtime, "require_supported_blender"):
                self.assertNotEqual(runtime.main(["run", "--log", str(script), str(script)]), 0)
            self.assertEqual(script.read_text(encoding="utf-8"), "pass")

    def test_existing_log_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            script, log = folder / "tool.py", folder / "existing.log"
            script.write_text("pass", encoding="utf-8")
            log.write_text("keep this", encoding="utf-8")
            with mock.patch.object(runtime, "require_supported_blender"):
                self.assertNotEqual(runtime.main(["run", "--log", str(log), str(script)]), 0)
            self.assertEqual(log.read_text(encoding="utf-8"), "keep this")

    @unittest.skipUnless(os.environ.get("BLENDER_TEST_PATH"), "set BLENDER_TEST_PATH for Blender integration test")
    def test_blender_inspection_preserves_unicode_source_hash(self):
        blender = Path(os.environ["BLENDER_TEST_PATH"])
        inspect_script = ROOT / "scripts" / "blender_inspect.py"
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "含 空格"
            folder.mkdir()
            source = folder / "open.obj"
            source.write_text("v 10 20 30\nv 12 20 30\nv 10 23 30\nf 1 2 3\n", encoding="utf-8")
            before = hashlib.sha256(source.read_bytes()).digest()
            report, log = folder / "报告.json", folder / "blender.log"
            result = subprocess.run([sys.executable, str(RUNTIME), "run", "--blender", str(blender),
                                     "--threads", "2", "--log", str(log), str(inspect_script), "--",
                                     "--input", str(source), "--output", str(report)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr + log.read_text(encoding="utf-8"))
            self.assertEqual(before, hashlib.sha256(source.read_bytes()).digest())
            data = json.loads(report.read_text(encoding="utf-8"))
            mesh = data["objects"][0]
            self.assertEqual(mesh["vertex_count"], 3)
            self.assertEqual(mesh["aabb_local"], {"min": [10.0, 20.0, 30.0], "max": [12.0, 23.0, 30.0]})
            self.assertEqual(mesh["topology"]["self_intersection"], "not_checked")

    @unittest.skipUnless(os.environ.get("BLENDER_TEST_PATH"), "set BLENDER_TEST_PATH for Blender integration test")
    def test_scaled_meshes_have_same_degeneracy_result_and_alias_is_safe(self):
        blender = Path(os.environ["BLENDER_TEST_PATH"])
        inspect_script = ROOT / "scripts" / "blender_inspect.py"
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "scale cases"
            folder.mkdir()
            for scale in (1e-6, 1e6):
                source = folder / ("mesh_%s.obj" % scale)
                source.write_text("v 0 0 0\nv %s 0 0\nv 0 %s 0\nf 1 2 3\n" % (scale, scale), encoding="utf-8")
                report, log = folder / ("report_%s.json" % scale), folder / ("log_%s.txt" % scale)
                result = subprocess.run([sys.executable, str(RUNTIME), "run", "--blender", str(blender),
                                         "--log", str(log), str(inspect_script), "--", "--input", str(source),
                                         "--output", str(report)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                topology = json.loads(report.read_text(encoding="utf-8"))["objects"][0]["topology"]
                self.assertEqual(topology["degenerate_face_count"], 0)
                self.assertEqual(topology["degenerate_tolerance_mode"], "extent_squared_relative")
            source = folder / "mesh_1e-06.obj"
            alias = folder / "source-alias.json"
            before = hashlib.sha256(source.read_bytes()).digest()
            try:
                os.link(source, alias)
            except OSError as exc:
                self.skipTest("hard links unavailable: %s" % exc)
            log = folder / "alias.log"
            result = subprocess.run([sys.executable, str(RUNTIME), "run", "--blender", str(blender),
                                     "--log", str(log), str(inspect_script), "--", "--input", str(source),
                                     "--output", str(alias)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(before, hashlib.sha256(source.read_bytes()).digest())


if __name__ == "__main__":
    unittest.main()
