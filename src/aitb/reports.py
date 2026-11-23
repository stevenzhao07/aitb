# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0
"""报告渲染：人读（md/html）+ 机器读（JUnit XML / SARIF v2.1.0 / JSON）。

为什么要有机器读的那两种：CI 面板（Jenkins / GitHub Actions / Azure DevOps）吃
JUnit XML，GitHub Code Scanning 吃 SARIF。没有这两种输出，别人的流水线里就接不上，
只能自己写适配器 —— 这是别人是否采纳的分水岭。
"""
import html
import json
import time
import xml.etree.ElementTree as ET

COLORS = {"PASS": "#7ee2a8", "FAIL": "#ff7b72", "SKIP": "#8b949e", "BLOCKED": "#d9a441"}
SARIF_LEVEL = {"FAIL": "error", "BLOCKED": "warning", "SKIP": "note"}


def render_markdown(preset, rows, counts):
    L = [f"# {preset.get('title', preset['name'])}", "",
         f"preset=`{preset['name']}` · profile=`{preset.get('profile', 'standard')}` · 生成时间见 run.json", "",
         "| 检查 | 类型 | 状态 | 码 | 依据 | 耗时 |", "|---|---|---|---|---|---|"]
    for v in rows:
        tag = " **【负控】**" if v.get("negative_control") else ""
        L.append(f"| {v['id']} | {v['type']} | **{v['status']}**{tag} | {v.get('code','')} "
                 f"| {v['why']} | {v['ms']} ms |")
    L += ["", f"合计：PASS {counts['PASS']} / FAIL {counts['FAIL']} / "
              f"SKIP {counts['SKIP']} / BLOCKED {counts['BLOCKED']}", "",
          "负控（`expect_status: FAIL`）的 FAIL 是按设计变红，证明这台子有能力变红，不是缺陷。", ""]
    if preset.get("notes"):
        L += ["## 边界", "", preset["notes"].strip(), ""]
    return "\n".join(L)


def render_html(preset, rows, counts, meta):
    trs = "".join(
        f"<tr><td class=i>{html.escape(v['id'])}"
        f"{' <span class=neg>负控</span>' if v.get('negative_control') else ''}</td>"
        f"<td class=t>{html.escape(str(v['type']))}</td>"
        f"<td class=c>{html.escape(v.get('code',''))}</td>"
        f"<td class=s style=color:{COLORS[v['status']]}>{v['status']}</td>"
        f"<td class=w>{html.escape(v['why'])}</td><td class=m>{v['ms']}</td></tr>" for v in rows)
    return f"""<!doctype html><meta charset=utf-8><title>{html.escape(preset.get('title','aitb'))}</title>
<style>body{{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;background:#0f1216;color:#e8eaed;margin:0;padding:32px}}
h1{{font-size:19px;margin:0 0 4px}}p.sub{{color:#8b949e;font-size:12.5px;margin:0 0 20px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}tr{{border-bottom:1px solid #23272e}}
td{{padding:9px 8px;vertical-align:top}}.i{{font-family:ui-monospace,Consolas,monospace;width:32%}}
.t{{color:#8b949e;width:8%}}.c{{color:#6e7681;width:8%;font-family:ui-monospace,Consolas,monospace}}
.s{{width:9%;font-weight:600}}.w{{color:#c9ccd1}}.m{{color:#6e7681;width:7%;text-align:right}}
.kpi{{display:flex;gap:22px;margin:0 0 20px;font-size:14px}}b{{font-size:20px;font-variant-numeric:tabular-nums}}
.neg{{font-size:10px;color:#d9a441;border:1px solid #6b4a1e;border-radius:9px;padding:1px 6px;margin-left:6px;vertical-align:2px}}</style>
<h1>{html.escape(preset.get('title','aitb'))}</h1>
<p class=sub>{html.escape(meta['run_id'])} · {html.escape(meta['os'])} · python {meta['python']} · aitb {meta.get('aitb_version','')}</p>
<div class=kpi><span>PASS <b style=color:#7ee2a8>{counts['PASS']}</b></span><span>FAIL <b style=color:#ff7b72>{counts['FAIL']}</b></span>
<span>SKIP <b style=color:#8b949e>{counts['SKIP']}</b></span><span>BLOCKED <b style=color:#d9a441>{counts['BLOCKED']}</b></span></div>
<table><tr><td class=i>检查</td><td class=t>类型</td><td class=c>码</td><td class=s>状态</td><td class=w>依据</td><td class=m>ms</td></tr>{trs}</table>"""


def render_json(rows, preset, counts):
    return json.dumps({"preset": preset["name"], "counts": counts, "verdicts": rows},
                      ensure_ascii=False, indent=1)


def render_junit(preset, rows, counts, meta):
    """JUnit XML：FAIL→failure，BLOCKED→error，SKIP→skipped，PASS→无子元素。

    BLOCKED 记为 error 而不是 failure：它不是"被测对象不合格"，是"这次没判到"——
    CI 面板里这两种要能分开看，否则统计出来的通过率是假的。
    """
    suite = ET.Element("testsuite", {
        "name": f"aitb.{preset['name']}",
        "tests": str(len(rows)),
        "failures": str(counts["FAIL"]),
        "errors": str(counts["BLOCKED"]),
        "skipped": str(counts["SKIP"]),
        "time": f"{sum(r['ms'] for r in rows) / 1000:.3f}",
        "timestamp": str(meta.get("started_at", "")),
        "hostname": str(meta.get("host", "")),
    })
    for r in rows:
        tc = ET.SubElement(suite, "testcase", {
            "classname": f"aitb.{preset['name']}",
            "name": r["id"],
            "time": f"{r['ms'] / 1000:.3f}",
        })
        msg = f"[{r.get('code','')}] {r['why']}"
        if r["status"] == "FAIL":
            el = ET.SubElement(tc, "failure", {"message": msg, "type": r.get("code", "FAIL")})
            el.text = r.get("evidence") or ""
        elif r["status"] == "BLOCKED":
            el = ET.SubElement(tc, "error", {"message": msg, "type": r.get("code", "BLOCKED")})
            el.text = r.get("evidence") or ""
        elif r["status"] == "SKIP":
            ET.SubElement(tc, "skipped", {"message": msg})
        props = ET.SubElement(tc, "properties")
        for k, v in (("aitb.status", r["status"]), ("aitb.code", r.get("code", "")),
                     ("aitb.type", str(r.get("type")),),
                     ("aitb.negative_control", str(bool(r.get("negative_control"))).lower())):
            ET.SubElement(props, "property", {"name": k, "value": v})
    root = ET.Element("testsuites")
    root.append(suite)
    return ET.tostring(root, encoding="unicode", xml_declaration=False)


def render_sarif(preset, rows, counts, meta, preset_uri=None):
    """SARIF v2.1.0：每条非 PASS 判定一条 result；PASS 不进 results（保持噪声为零）。"""
    rules, results = [], []
    for r in rows:
        if r["status"] == "PASS":
            continue
        rules.append({
            "id": r["id"],
            "shortDescription": {"text": f"{r.get('type')} 检查：{r['id']}"},
            "fullDescription": {"text": r["why"]},
            "properties": {"aitbStatus": r["status"], "aitbCode": r.get("code", ""),
                           "negativeControl": bool(r.get("negative_control"))},
        })
        results.append({
            "ruleId": r["id"],
            "ruleIndex": len(rules) - 1,
            "level": SARIF_LEVEL.get(r["status"], "warning"),
            "message": {"text": f"[{r.get('code','')}] {r['why']}"},
            "properties": {"aitbStatus": r["status"], "aitbCode": r.get("code", ""),
                           "durationMs": r["ms"]},
        })
    invocation = {
        "executionSuccessful": counts["FAIL"] == 0,
        "startTimeUtc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "commandLine": f"aitb run {preset['name']}" + (" --strict" if meta.get("strict") else ""),
    }
    if preset_uri:
        invocation["arguments"] = [preset_uri]
    log = {
        "$schema": "https://docs.oasis-open.org/sarif/sarif/v2.1.0/os/schemas/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {
                "name": "aitb", "fullName": "AITB — Assurance Instrument Test Bench",
                "semanticVersion": str(meta.get("aitb_version", "0.0.0")),
                "informationUri": "https://github.com/stevenzhao07/aitb",
                "rules": rules,
            }},
            "invocations": [invocation],
            "results": results,
            "properties": {"preset": preset["name"], "counts": counts},
        }],
    }
    return json.dumps(log, ensure_ascii=False, indent=1)
