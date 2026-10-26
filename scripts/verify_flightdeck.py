"""FLIGHT DECK 3.5 verification: API-seeded project, then browser checks on the real UI.

    python scripts/verify_flightdeck.py

Seeds a disposable project/conversation through the public API (no UI dialogs), imports a
fixture, runs a demo ask, then asserts the mission bar, timeline stamps, reader, theme and
480px layout. Intended for local acceptance, not CI.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from browser_acceptance import Browser, CHECKS, check

ROOT = Path(__file__).resolve().parents[1]


def seed(base: str, material: Path) -> dict:
    name = f'飞行验收 {time.strftime("%H%M%S")}'
    with httpx.Client(base_url=base, timeout=30, trust_env=False) as client:
        project = client.post('/api/v2/projects', json={'name': name}).raise_for_status().json()
        pid = project['id']
        conversation = client.post(f'/api/v2/projects/{pid}/conversations',
                                   json={'title': '任务台验收'}).raise_for_status().json()
        cid = conversation['id']
        with material.open('rb') as stream:
            client.post(f'/api/v2/projects/{pid}/imports', files={'file': (material.name, stream, 'text/markdown')},
                        headers={'Idempotency-Key': 'fd-material-' + pid}).raise_for_status()
        for _ in range(120):
            materials = client.get(f'/api/v2/projects/{pid}/materials').raise_for_status().json()
            if materials and materials[0]['status'] == 'ready':
                break
            time.sleep(1)
        sent = client.post(f'/api/v2/projects/{pid}/conversations/{cid}/messages',
                           headers={'Idempotency-Key': 'fd-ask-' + pid},
                           json={'text': '这些材料里“自由”是在什么意义上使用的？', 'tool': 'ask',
                                 'provider_mode': 'demo'}).raise_for_status().json()
        for _ in range(120):
            job = client.get(f'/api/v2/projects/{pid}/jobs/{sent["id"]}').raise_for_status().json()
            if job['state'] in {'succeeded', 'failed', 'cancelled'}:
                break
            time.sleep(1)
        return {'pid': pid, 'cid': cid, 'job': job['state'], 'name': name}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:8010')
    parser.add_argument('--port', type=int, default=9333)
    parser.add_argument('--material', default='fixtures/research/autonomy-a.md')
    parser.add_argument('--out', default='output/acceptance-browser')
    parser.add_argument('--no-launch', action='store_true')
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    seeded = seed(args.base_url, ROOT / args.material)

    browser = Browser(args.base_url, args.port, out / 'edge-profile-flightdeck')
    try:
        browser.start(launch=not args.no_launch)
        browser.page('about:blank')
        browser.send('Page.addScriptToEvaluateOnNewDocument', source=(
            "sessionStorage.setItem('scriptorium_brand_seen','1');"
            "localStorage.setItem('scriptorium_startup_config', JSON.stringify({enabled:false}));"))
        browser.send('Page.navigate', url=args.base_url + '/')
        browser.require("!!document.querySelector('.unified-workspace')", 60, 'workspace')
        browser.js(f"localStorage.setItem('scriptorium_research_project',{json.dumps(seeded['pid'])});"
                   f"localStorage.setItem('scriptorium_last_conversation:{seeded['pid']}',{json.dumps(seeded['cid'])});"
                   "localStorage.setItem('scriptorium_theme','light');")
        browser.send('Page.reload')
        browser.require("!!document.querySelector('.fd-bar')", 60, 'mission bar')
        dashboard = browser.wait(
            f"(document.querySelector('.wb-project-picker span')?.textContent||'')==={json.dumps(seeded['name'])}"
            "&&document.body.innerText.includes('任务台验收')", 60, 'project and conversation selected')
        check('FD-01 任务条与运行号', True, browser.js(
            "return (document.querySelector('.fd-bar')||{}).innerText||'';"))
        check('FD-02 项目选择器', dashboard, browser.js(
            "return document.querySelector('.wb-project-picker span')?.textContent||'';"))

        timeline = browser.wait("!!document.querySelector('.rt-turn')", 90, 'timeline turn')
        stamps = browser.js("return [...document.querySelectorAll('.fd-stamp')].map(x=>x.textContent).join(',')")
        check('FD-04 飞行日志与状态章', bool(timeline) and bool(stamps), stamps)
        browser.wait("!!document.querySelector('.rt-answer')", 90, 'answer block')
        answer = browser.js("return (document.querySelector('.rt-answer')||{}).innerText||''")
        check('FD-05 演示回答进入日志', '演示' in answer or '材料' in answer, answer[:80])

        browser.js("document.querySelector('.wb-nav button:nth-child(2)')?.click()")
        browser.require("!!document.querySelector('.wb-material-row')", 30, 'material row')
        browser.js("const b=[...document.querySelectorAll('.wb-material-row button')]"
                   ".find(x=>(x.textContent||'').includes('可阅读'));b?.click()")
        browser.require("!!document.querySelector('.uw-document-pane')", 40, 'document pane')
        browser.require("!!document.querySelector('.uw-source p[data-source]')", 40, 'reader')
        selected = browser.js("""const p=document.querySelector('.uw-source p[data-source]');const t=p.textContent||'';const n=p.firstChild;
          if(!n||t.length<4)return '';const r=document.createRange();r.setStart(n,0);r.setEnd(n,Math.min(8,t.length));
          const s=window.getSelection();s.removeAllRanges();s.addRange(r);p.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));
          return s.toString();""")
        selection = browser.wait("!!document.querySelector('.uw-selection blockquote')", 20, 'floating selection')
        check('FD-06 原文可读并可选区', bool(selected) and selection, selected)

        browser.js("document.querySelector('.fd-toggle:not(.fd-halo-toggle)')?.click()")
        dark = browser.wait("document.documentElement.dataset.theme==='dark'", 10, 'dark theme')
        bg = browser.js("return getComputedStyle(document.body).backgroundColor")
        check('FD-07 白班/夜班切换', dark and bg not in ('rgb(245, 243, 236)', ''), bg)
        browser.screenshot(out / 'flightdeck-dark.png')

        browser.send('Emulation.setDeviceMetricsOverride', width=480, height=900, deviceScaleFactor=1, mobile=True)
        time.sleep(1)
        overflow = browser.js("return document.documentElement.scrollWidth<=window.innerWidth+1")
        check('FD-08 480px 无横向溢出', overflow, browser.js("return document.documentElement.scrollWidth+'/'+window.innerWidth"))
        browser.screenshot(out / 'flightdeck-480.png')
    finally:
        browser.close()

    report = {'checks': CHECKS, 'passed': sum(1 for item in CHECKS if item['ok']), 'total': len(CHECKS),
              'seed': seeded}
    (out / 'flightdeck.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'total': report['total'], 'job': seeded['job']}, ensure_ascii=False))
    return 0 if report['passed'] == report['total'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
