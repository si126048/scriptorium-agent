"""Desktop bootstrap check: fake Tauri bridge drives first-run install → connect → workspace.

    python scripts/desktop_bootstrap_check.py

The fake bridge never touches the machine: it only answers `research_status`,
`research_start` and `get_research_connection`, so this verifies the gate UI and the wiring
without downloading PostgreSQL.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from browser_acceptance import Browser, CHECKS, check

BRIDGE = """(function(){
  window.__calls=[]; let started=false, polls=0;
  localStorage.removeItem('scriptorium_desktop_install');
  window.__TAURI_INTERNALS__={invoke:(name,args)=>{
    window.__calls.push([name,args]);
    if(name==='research_status'){
      polls++;
      if(!started)return Promise.resolve({installed:false,state:'not_installed',search:true,online:false});
      if(polls<4)return Promise.resolve({installed:true,state:'installing',phase:'postgres',search:false,online:false});
      if(polls<6)return Promise.resolve({installed:true,state:'starting',phase:'api',search:false,online:false,error:null});
      return Promise.resolve({installed:true,state:'running',phase:'done',search:false,online:true,url:'http://127.0.0.1:8010',api_port:8010});
    }
    if(name==='research_start'){ started=true; return Promise.resolve(null); }
    if(name==='get_research_connection'){
      return Promise.resolve({url:'http://127.0.0.1:8010',api_key:'',search:false});
    }
    if(name==='set_research_service')return Promise.resolve(null);
    if(name==='research_open_logs')return Promise.resolve('C:/logs');
    return Promise.resolve(null);
  }};
  sessionStorage.setItem('scriptorium_brand_seen','1');
})();"""

FAIL_BRIDGE = """(function(){
  window.__TAURI_INTERNALS__={invoke:(name)=>{
    if(name==='research_status')return Promise.resolve({installed:true,state:'failed',phase:null,
      error:'LOCAL_DEPENDENCY_START_TIMEOUT',search:true,online:false});
    if(name==='research_start')return Promise.resolve(null);
    return Promise.resolve(null);
  }};
  sessionStorage.setItem('scriptorium_brand_seen','1');
})();"""


def open_page(browser: Browser, base_url: str, init: str, path: str = '/') -> None:
    browser.page('about:blank')
    browser.send('Page.addScriptToEvaluateOnNewDocument', source=init)
    browser.send('Page.navigate', url=base_url + path)
    browser.require(f"location.origin==={json.dumps(base_url)}", 30, 'page origin')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:8010')
    parser.add_argument('--port', type=int, default=9333)
    parser.add_argument('--out', default='output/acceptance-browser')
    parser.add_argument('--no-launch', action='store_true')
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    browser = Browser(args.base_url, args.port, out / 'edge-profile-bootstrap')
    try:
        browser.start(launch=not args.no_launch)
        # First run: the gate must offer full/lite setup before touching the workspace.
        open_page(browser, args.base_url, BRIDGE)
        browser.require("document.body.innerText.includes('本机研究工作台')", 40, 'gate visible')
        first_run = browser.js("return document.body.innerText.includes('精简安装')&&document.body.innerText.includes('完整安装')")
        check('DESKTOP-01 首次启动显示一键安装选项', first_run, '精简 / 完整安装')
        browser.screenshot(out / '12-desktop-first-run.png')

        clicked = browser.js(
            "return (()=>{const b=[...document.querySelectorAll('button')].find(x=>x.textContent.includes('精简安装'));"
            "if(!b)return false;b.click();return true;})()")
        started = browser.wait(
            "window.__calls.some(c=>c[0]==='research_start' && c[1] && c[1].search===false)", 15, 'lite start called')
        check('DESKTOP-02 精简安装以 search=false 启动', bool(clicked) and started, 'research_start(search=false)')
        progress = browser.wait("document.body.innerText.includes('启动研究工作台服务')||document.body.innerText.includes('下载并解压 PostgreSQL')",
                                20, 'progress phase visible')
        check('DESKTOP-03 显示安装/启动进度', progress, '阶段文案可见')
        browser.screenshot(out / '13-desktop-progress.png')

        workspace = browser.wait("!!document.querySelector('.unified-workspace')", 40, 'workspace after bootstrap')
        check('DESKTOP-04 服务就绪后自动进入工作台', workspace, 'workspace mounted')

        projects = browser.wait("(document.querySelector('.wb-project-picker span')?.textContent||'').length>0",
                                30, 'projects loaded through the connected service')
        check('DESKTOP-05 前端与后端连接畅通', projects, '项目列表来自 8010')

        # Failure path: clear first-run choice and make the runtime report a hard failure.
        browser.js("localStorage.removeItem('scriptorium_desktop_install')")
        open_page(browser, args.base_url, FAIL_BRIDGE)
        failed = browser.wait("document.body.innerText.includes('重试启动')", 40, 'retry shown')
        message = browser.js("return document.body.innerText.includes('LOCAL_DEPENDENCY_START_TIMEOUT')")
        check('DESKTOP-06 启动失败给出错误与重试', failed and message, '错误码 + 重试按钮')
        browser.screenshot(out / '14-desktop-failed.png')
    finally:
        browser.close()

    report = {'checks': CHECKS, 'passed': sum(1 for item in CHECKS if item['ok']), 'total': len(CHECKS)}
    (out / 'desktop-bootstrap.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'total': report['total']}, ensure_ascii=False))
    return 0 if report['passed'] == report['total'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
