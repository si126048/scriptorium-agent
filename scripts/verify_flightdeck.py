"""FLIGHT DECK verification: five stable checks on the real 3.5 workbench.

    python scripts/verify_flightdeck.py

Seeds a disposable project, one material and one demo ask through the public API, then verifies
the mission bar, project picker, flight log, theme switch and 480px layout. Kept intentionally
short so it can run locally without flaky long flows.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from browser_acceptance import Browser, CHECKS, check, set_value

ROOT = Path(__file__).resolve().parents[1]


def seed(base: str, material: Path) -> dict:
    name = f'飞行验收 {time.strftime("%H%M%S")}'
    with httpx.Client(base_url=base, timeout=30, trust_env=False) as client:
        project = client.post('/api/v2/projects', json={'name': name}).raise_for_status().json()
        pid = project['id']
        cid = client.post(f'/api/v2/projects/{pid}/conversations',
                          json={'title': '任务台验收'}).raise_for_status().json()['id']
        with material.open('rb') as stream:
            client.post(f'/api/v2/projects/{pid}/imports',
                        files={'file': (material.name, stream, 'text/markdown')},
                        headers={'Idempotency-Key': 'fd-material-' + pid}).raise_for_status()
        for _ in range(120):
            rows = client.get(f'/api/v2/projects/{pid}/materials').raise_for_status().json()
            if rows and rows[0]['status'] == 'ready':
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
        return {'pid': pid, 'cid': cid, 'name': name, 'job': job['state']}


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
    if seeded['job'] != 'succeeded':
        print(json.dumps({'error': 'seed job ' + seeded['job']}, ensure_ascii=False))
        return 1

    shutil.rmtree(out / 'edge-profile-flightdeck', ignore_errors=True)
    browser = Browser(args.base_url, args.port, out / 'edge-profile-flightdeck')
    try:
        browser.start(launch=not args.no_launch)
        browser.page('about:blank')
        init = (
            "sessionStorage.setItem('scriptorium_brand_seen','1');"
            "localStorage.setItem('scriptorium_startup_config', JSON.stringify({enabled:false}));"
            "localStorage.setItem('scriptorium_theme','light');"
            f"localStorage.setItem('scriptorium_research_project',{json.dumps(seeded['pid'])});"
            f"localStorage.setItem('scriptorium_last_conversation:{seeded['pid']}',{json.dumps(seeded['cid'])});"
        )
        browser.send('Page.addScriptToEvaluateOnNewDocument', source=init)
        browser.send('Network.enable')
        browser.send('Network.setCacheDisabled', cacheDisabled=True)
        browser.send('Page.navigate', url=args.base_url + '/?fd=' + str(int(time.time())))
        browser.require("!!document.querySelector('.fd-bar')", 60, 'mission bar')
        check('FD-01 任务条', True, browser.js("return (document.querySelector('.fd-bar')||{}).innerText||'';"))
        selected = browser.wait(
            f"(document.querySelector('.wb-project-picker span')?.textContent||'')==={json.dumps(seeded['name'])}",
            60, 'project selected')
        check('FD-02 项目选择器', selected, browser.js(
            "return document.querySelector('.wb-project-picker span')?.textContent||'';"))
        snapshot = browser.js(f"return (async()=>{{const r=await fetch('/api/v2/projects/{seeded['pid']}/conversations/{seeded['cid']}/snapshot');const j=await r.json();return r.status+':'+(j.blocks||[]).length;}})()")
        check('FD-03 时间线快照可读', str(snapshot).startswith('200:')
              and int(str(snapshot).split(':')[1] or 0) > 0, snapshot)
        browser.js("const b=[...document.querySelectorAll('.wb-nav button')].find(x=>(x.textContent||'').includes('项目材料'));b?.click()")
        browser.require("!!document.querySelector('.wb-material-row')", 40, 'material list')
        browser.js("const b=document.querySelector('.wb-material-row button');b?.click()")
        browser.require("!!document.querySelector('.uw-source p[data-source]')", 60, 'reader')
        check('FD-04 原文阅读器', True, browser.js(
            "return document.querySelectorAll('.uw-source p[data-source]').length + ' segments';"))
        selected = browser.js("""const p=document.querySelector('.uw-source p[data-source]');const t=p.textContent||'';const n=p.firstChild;
          if(!n||t.length<4)return '';const r=document.createRange();r.setStart(n,0);r.setEnd(n,Math.min(8,t.length));
          const s=window.getSelection();s.removeAllRanges();s.addRange(r);p.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));
          return s.toString();""")
        selection = browser.wait("!!document.querySelector('.uw-selection blockquote')", 20, 'floating selection')
        check('FD-05 原文选区', bool(selected) and selection, selected)

        set_value(browser, '.uw-selection textarea', '验收笔记：先记录当前理解。')
        browser.js("const b=[...document.querySelectorAll('.uw-selection button')].find(x=>(x.textContent||'').includes('保存笔记与证据'));b?.click()")
        browser.require("!!document.querySelector('.wb-artifact')", 60, 'note artifact')
        note = browser.js("return (document.querySelector('.wb-artifact')||{}).innerText||''")
        check('FD-06 选区保存笔记与证据', '验收笔记' in note, note[:80])
        browser.js("document.querySelector('.wb-source-strip button')?.click()")
        browser.require("!!document.querySelector('.uw-source mark')", 60, 'evidence highlight')
        check('FD-07 证据回跳原文高亮', True, browser.js(
            "return (document.querySelector('.uw-source mark')||{}).textContent||'';"))
        browser.js("const tabs=[...document.querySelectorAll('.wb-document-tab')];tabs.at(-1)?.querySelector('button')?.click()")
        browser.require("!!document.querySelector('.wb-artifact')", 30, 'note tab')
        browser.js("document.querySelector('[aria-label=\"导出文稿\"]')?.click()")
        export_panel = browser.wait("!!document.querySelector('.wb-inspector')", 20, 'export panel')
        check('FD-08 导出面板', export_panel, browser.js(
            "return (document.querySelector('.wb-inspector')||{}).innerText||'';"))

        light_contrast = browser.js("""const rgb=c=>{const n=(c.match(/[0-9.]+/g)||[]).map(Number);return n.slice(0,3)};
        const lum=v=>{v=v.map(x=>{x/=255;return x<=.03928?x/12.92:Math.pow((x+.055)/1.055,2.4)});return .2126*v[0]+.7152*v[1]+.0722*v[2]};
        const bg=e=>{while(e){const c=getComputedStyle(e).backgroundColor;const n=(c.match(/[0-9.]+/g)||[]).map(Number);if(n.length>=3&&(n.length<4||n[3]>.9))return n.slice(0,3);e=e.parentElement}return [255,255,255]};
        const ratio=(a,b)=>{const l1=lum(a),l2=lum(b);return (Math.max(l1,l2)+.05)/(Math.min(l1,l2)+.05)};
        const sels=['.fd-crumb h1','.fd-status','.rt-answer','.wb-session.selected','.wb-document-title'];
        return sels.map(s=>{const e=document.querySelector(s);if(!e)return s+':missing';return s+':'+ratio(rgb(getComputedStyle(e).color),bg(e)).toFixed(2)}).join(',');""")
        light_values = [float(x.split(':')[1]) for x in light_contrast.split(',') if ':missing' not in x]
        check('FD-09 白班对比度（AA 4.5）', bool(light_values) and min(light_values) >= 4.5, light_contrast)

        browser.js("document.querySelector('.fd-toggle:not(.fd-halo-toggle)')?.click()")
        dark = browser.wait("document.documentElement.dataset.theme==='dark'", 10, 'night shift')
        dark_contrast = browser.js("""const rgb=c=>{const n=(c.match(/[0-9.]+/g)||[]).map(Number);return n.slice(0,3)};
        const lum=v=>{v=v.map(x=>{x/=255;return x<=.03928?x/12.92:Math.pow((x+.055)/1.055,2.4)});return .2126*v[0]+.7152*v[1]+.0722*v[2]};
        const bg=e=>{while(e){const c=getComputedStyle(e).backgroundColor;const n=(c.match(/[0-9.]+/g)||[]).map(Number);if(n.length>=3&&(n.length<4||n[3]>.9))return n.slice(0,3);e=e.parentElement}return [255,255,255]};
        const ratio=(a,b)=>{const l1=lum(a),l2=lum(b);return (Math.max(l1,l2)+.05)/(Math.min(l1,l2)+.05)};
        const sels=['.fd-crumb h1','.fd-status','.rt-answer','.wb-session.selected','.wb-document-title'];
        return sels.map(s=>{const e=document.querySelector(s);if(!e)return s+':missing';return s+':'+ratio(rgb(getComputedStyle(e).color),bg(e)).toFixed(2)}).join(',');""")
        dark_values = [float(x.split(':')[1]) for x in dark_contrast.split(',') if ':missing' not in x]
        check('FD-11 夜班对比度（AA 4.5）', bool(dark_values) and min(dark_values) >= 4.5, dark_contrast)
        check('FD-10 白班/夜班切换', dark, browser.js("return document.documentElement.dataset.theme||'';"))
        browser.screenshot(out / 'flightdeck-dark.png')
        browser.send('Emulation.setDeviceMetricsOverride', width=480, height=900, deviceScaleFactor=1, mobile=True)
        time.sleep(1)
        overflow = browser.js("return document.documentElement.scrollWidth<=window.innerWidth+1")
        check('FD-12 480px 无横向溢出', overflow,
              browser.js("return document.documentElement.scrollWidth+'/'+window.innerWidth"))
        browser.screenshot(out / 'flightdeck-480.png')
    finally:
        browser.close()

    report = {'checks': CHECKS, 'passed': sum(1 for item in CHECKS if item['ok']), 'total': len(CHECKS),
              'seed': seeded}
    (out / 'flightdeck.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'total': report['total']}, ensure_ascii=False))
    return 0 if report['passed'] == report['total'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
