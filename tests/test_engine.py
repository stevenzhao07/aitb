# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0
"""回归测试（只用标准库 unittest，CI 不需要装 pytest）。

跑法：python -m unittest discover -s tests -v
"""
import json
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aitb import adapters, engine, paths, reports, variables  # noqa: E402


def write_preset(dirpath, name, checks, **kw):
    data = {"name": name, "checks": checks}
    data.update(kw)
    p = Path(dirpath) / f"{name}.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


class PresetValidation(unittest.TestCase):
    def test_accepts_wellformed(self):
        p = {"name": "demo", "checks": [{"id": "demo.ok", "type": "cmd", "cmd": "python -c print(1)"}]}
        self.assertEqual(engine.validate_preset(p), [])

    def test_rejects_duplicate_id(self):
        p = {"name": "demo", "checks": [{"id": "demo.a", "type": "cmd", "cmd": "x"},
                                        {"id": "demo.a", "type": "cmd", "cmd": "y"}]}
        self.assertIn("E002", [c for c, _ in engine.validate_preset(p)])

    def test_rejects_unknown_adapter(self):
        p = {"name": "demo", "checks": [{"id": "demo.a", "type": "nope"}]}
        self.assertIn("E003", [c for c, _ in engine.validate_preset(p)])

    def test_rejects_missing_required_field(self):
        p = {"name": "demo", "checks": [{"id": "demo.a", "type": "files"}]}
        self.assertIn("E004", [c for c, _ in engine.validate_preset(p)])

    def test_rejects_bad_expect_status(self):
        p = {"name": "demo", "checks": [{"id": "demo.a", "type": "cmd", "cmd": "x",
                                         "expect_status": "MAYBE"}]}
        self.assertIn("E005", [c for c, _ in engine.validate_preset(p)])

    def test_rejects_empty_checks(self):
        p = {"name": "demo", "checks": []}
        self.assertIn("E001", [c for c, _ in engine.validate_preset(p)])

    def test_rejects_bad_id(self):
        p = {"name": "demo", "checks": [{"id": "Demo.Bad", "type": "cmd", "cmd": "x"}]}
        self.assertIn("E008", [c for c, _ in engine.validate_preset(p)])


class VariableExpansion(unittest.TestCase):
    def test_expands_and_detects_missing(self):
        v = {"A": "one", "AITB_PKG": paths.PKG}
        self.assertEqual(variables.expand("x-${A}-y", v), "x-one-y")
        self.assertEqual(variables.unresolved(variables.expand("${B}", v)), ["B"])

    def test_builtin_vars_always_available(self):
        b = variables.builtin_vars()
        for k in ("AITB_PKG", "AITB_ROOT", "AITB_RUNS"):
            self.assertIn(k, b)

    def test_missing_vars_raise(self):
        with self.assertRaises(variables.MissingVars):
            raise variables.MissingVars(["X"], "cfg.json")


class Execute(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aitb-test-"))
        self.runs = self.tmp / "runs"

    def _run(self, checks, **kw):
        name = kw.pop("name", "t")
        preset = {"name": name, "checks": checks}
        return engine.execute(preset, runs=self.runs, echo=False, **kw)

    def test_pass_and_manifest(self):
        r = self._run([{"id": "t.pass", "type": "cmd", "cmd": "python -c \"print('OK')\"", "expect": "OK"}])
        self.assertEqual(r.counts["PASS"], 1)
        self.assertEqual(r.rc, engine.EXIT_OK)
        names = {f.name for f in r.rdir.iterdir()}
        self.assertTrue({"run.json", "verdicts.json", "report.md", "snapshot.html",
                         "manifest.json"} <= names)
        mf = json.loads((r.rdir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(mf["files"]), 4)

    def test_failure_sets_nonzero_exit(self):
        r = self._run([{"id": "t.fail", "type": "cmd", "cmd": "python -c \"print('no')\"", "expect": "yes"}])
        self.assertEqual(r.counts["FAIL"], 1)
        self.assertEqual(r.rc, engine.EXIT_FAIL)
        self.assertEqual(r.verdicts[0]["code"], "V101")

    def test_negative_control_by_design(self):
        r = self._run([{"id": "t.neg", "type": "cmd", "cmd": "python -c \"print('x')\"",
                        "expect": "never", "expect_status": "FAIL"}])
        self.assertTrue(r.by_design)
        self.assertTrue(r.verdicts[0]["negative_control"])

    def test_negative_control_inverted_is_caught(self):
        r = self._run([{"id": "t.neg", "type": "cmd", "cmd": "python -c \"print('hit')\"",
                        "expect": "hit", "expect_status": "FAIL"}])
        self.assertFalse(r.by_design)
        self.assertEqual(r.verdicts[0]["code"], "V107")

    def test_skip_not_pass_and_strict_codes(self):
        checks = [{"id": "t.net", "type": "http", "needs_network": True,
                   "targets": [{"url": "https://example.invalid/"}]}]
        soft = self._run(checks, offline=True)
        self.assertEqual(soft.counts["SKIP"], 1)
        self.assertEqual(soft.rc, engine.EXIT_OK)
        strict = self._run(checks, offline=True, strict=True, name="t2")
        self.assertEqual(strict.rc, engine.EXIT_STRICT_INCOMPLETE)

    def test_files_min_size_rejects_empty(self):
        empty = self.tmp / "empty.txt"
        empty.write_bytes(b"")
        r = self._run([{"id": "t.size", "type": "files",
                        "paths": [{"path": str(empty), "min_size": 100}]}])
        self.assertEqual(r.verdicts[0]["code"], "V104")
        self.assertEqual(r.rc, engine.EXIT_FAIL)

    def test_relative_cwd_resolves_against_root(self):
        old = os.environ.get("AITB_ROOT")
        os.environ["AITB_ROOT"] = str(self.tmp)
        try:
            (self.tmp / "sub").mkdir()
            r = self._run([{"id": "t.cwd", "type": "cmd", "cwd": "sub",
                            "cmd": "python -c \"import os;print(os.getcwd())\""}])
            self.assertEqual(r.counts["PASS"], 1)
        finally:
            if old is None:
                os.environ.pop("AITB_ROOT", None)
            else:
                os.environ["AITB_ROOT"] = old


class Formats(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {"id": "a.pass", "type": "cmd", "status": "PASS", "code": "V001", "why": "ok",
             "evidence": "", "ms": 12, "negative_control": False},
            {"id": "a.fail", "type": "cmd", "status": "FAIL", "code": "V101", "why": "missing",
             "evidence": "tail", "ms": 20, "negative_control": False},
            {"id": "a.block", "type": "files", "status": "BLOCKED", "code": "V201", "why": "timeout",
             "evidence": "", "ms": 0, "negative_control": False},
            {"id": "a.skip", "type": "http", "status": "SKIP", "code": "V301", "why": "offline",
             "evidence": "", "ms": 0, "negative_control": False},
        ]
        self.counts = {"PASS": 1, "FAIL": 1, "SKIP": 1, "BLOCKED": 1}
        self.preset = {"name": "fmt", "title": "格式"}
        self.meta = {"run_id": "r1", "started_at": "2026-01-01T00:00:00Z", "host": "h",
                     "aitb_version": "0.1.0", "strict": False}

    def test_junit_is_well_formed_and_maps_states(self):
        xml = reports.render_junit(self.preset, self.rows, self.counts, self.meta)
        root = ET.fromstring(xml)
        suite = root.find("testsuite")
        self.assertEqual(suite.get("tests"), "4")
        self.assertEqual(suite.get("failures"), "1")
        self.assertEqual(suite.get("errors"), "1")     # BLOCKED 记 error，不混入 failure
        self.assertEqual(suite.get("skipped"), "1")
        cases = {c.get("name"): c for c in suite.findall("testcase")}
        self.assertIsNotNone(cases["a.fail"].find("failure"))
        self.assertIsNotNone(cases["a.block"].find("error"))
        self.assertIsNotNone(cases["a.skip"].find("skipped"))
        self.assertIsNone(cases["a.pass"].find("failure"))

    def test_sarif_shape(self):
        log = json.loads(reports.render_sarif(self.preset, self.rows, self.counts, self.meta))
        self.assertEqual(log["version"], "2.1.0")
        run = log["runs"][0]
        self.assertEqual(run["tool"]["driver"]["name"], "aitb")
        levels = {r["ruleId"]: r["level"] for r in run["results"]}
        self.assertNotIn("a.pass", levels)              # PASS 不进 results
        self.assertEqual(levels["a.fail"], "error")
        self.assertEqual(levels["a.block"], "warning")
        self.assertEqual(levels["a.skip"], "note")

    def test_markdown_mentions_negative_control(self):
        rows = [dict(self.rows[1], negative_control=True)]
        md = reports.render_markdown(self.preset, rows, {"PASS": 0, "FAIL": 1, "SKIP": 0, "BLOCKED": 0})
        self.assertIn("负控", md)


class DocsContract(unittest.TestCase):
    """T4 的仓库侧：内置预设、包内索引、README 三处必须对得上。"""

    def setUp(self):
        self.repo = Path(__file__).resolve().parents[1]
        self.pkg = self.repo / "src" / "aitb"

    def test_index_matches_presets_on_disk(self):
        idx = json.loads((self.pkg / "presets" / "_index.json").read_text(encoding="utf-8"))["presets"]
        have = sorted(p.stem for p in (self.pkg / "presets").glob("*.json")
                      if not p.name.startswith("_"))
        self.assertEqual(sorted(idx), have)

    def test_readme_lists_every_bundled_preset(self):
        readme = (self.repo / "README.md").read_text(encoding="utf-8")
        have = sorted(p.stem for p in (self.pkg / "presets").glob("*.json")
                      if not p.name.startswith("_"))
        for name in have:
            self.assertIn(f"`{name}`", readme, f"README 没提到内置预设 {name}")

    def test_license_and_spdx_headers(self):
        self.assertTrue((self.repo / "LICENSE").read_text(encoding="utf-8").strip().startswith("Apache License"))
        missing = []
        for f in list(self.pkg.rglob("*.py")) + list((self.repo / "tests").rglob("*.py")):
            head = "\n".join(f.read_text(encoding="utf-8").splitlines()[:2])
            if "SPDX-License-Identifier: Apache-2.0" not in head:
                missing.append(str(f.relative_to(self.repo)))
        self.assertEqual(missing, [], f"缺 SPDX 头的文件：{missing}")


class AdapterContract(unittest.TestCase):
    def test_all_builtin_adapters_return_five_tuple(self):
        empty = tempfile.NamedTemporaryFile(suffix=".txt", delete=False)
        empty.write(b"hello world")
        empty.close()
        st, code, why, ev, ms = adapters.a_files({"paths": [{"path": empty.name}]}, {})
        self.assertEqual(len((st, code, why, ev, ms)), 5)
        self.assertEqual(st, "PASS")

    def test_plugin_registration(self):
        adapters.register("dummy_test_adapter", lambda spec, ctx: ("PASS", "V001", "ok", "", 0))
        self.assertIn("dummy_test_adapter", adapters.ADAPTERS)


if __name__ == "__main__":
    unittest.main()
