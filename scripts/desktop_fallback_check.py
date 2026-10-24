"""Regression check: a desktop IPC that never answers must not freeze the workbench.

Injects a Tauri bridge whose `get_research_connection` never resolves, then verifies that the
workspace still renders, falls back to the local service address, and the model settings form
becomes usable (no endless "正在读取模型设置"). Screenshot: 11-desktop-ipc-fallback.png.

    python scripts/desktop_fallback_check.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from browser_acceptance import Browser, CHECKS, check, click_text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:8010')
    parser.add_argument('--port', type=int, default=9333)
    parser.add_argument('--out', default='output/acceptance-browser')
    parser.add_argument('--no-launch', action='store_true')
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    browser = Browser(args.base_url, args.port, out / 'edge-profile')
    try:
        browser.start(launch=not args.no_launch)
        browser.page('about:blank')
        browser.send('Page.addScriptToEvaluateOnNewDocument', source=(
            "window.__TAURI_INTERNALS__={invoke:()=>new Promise(()=>{})};"
            "sessionStorage.setItem('scriptorium_brand_seen','1');"))
        browser.send('Page.navigate', url=args.base_url + '/')
        browser.require(f"location.origin==={json.dumps(args.base_url)}", 30, 'fallback page')
        browser.require("!!document.querySelector('.unified-workspace')", 60, 'workspace rendered')
        check('IPC-01 桌面 IPC 无响应时界面仍可用', True, 'workspace rendered')
        browser.require("!!document.querySelector('.uw-sidebar select')&&!!document.querySelector('.uw-sidebar select').value",
                        30, 'project restored')
        # The restored conversation may switch panels after the first click, so keep opening
        # settings until the form is actually on screen.
        loaded = browser.wait(
            "(()=>{const b=[...document.querySelectorAll('.uw-sidebar-bottom button')]"
            ".find(x=>x.textContent.includes('设置与档案'));if(b)b.click();"
            "return !!document.querySelector('select[aria-label=\"模型服务商\"]');})()",
            40, 'model settings after hung IPC')
        warned = browser.wait("document.body.innerText.includes('未能从桌面进程取得研究服务地址')", 10,
                              'fallback warning')
        click_text(browser, '.uw-sidebar-bottom button', '设置与档案')
        check('IPC-02 模型设置不再无限加载', loaded, '模型表单可用')
        check('IPC-03 明确提示已回退服务地址', warned, '设置页显示回退提示')
        browser.screenshot(out / '11-desktop-ipc-fallback.png')
    finally:
        browser.close()

    report = {'checks': CHECKS, 'passed': sum(1 for item in CHECKS if item['ok']), 'total': len(CHECKS)}
    (out / 'desktop-fallback.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'total': report['total']}, ensure_ascii=False))
    return 0 if report['passed'] == report['total'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
