"""Browser acceptance for the unified workbench, driven through the Chrome DevTools Protocol.

It uses the locally installed Microsoft Edge in headless mode: no extra packages, no network.
Every step prints PASS/FAIL with the observed value and saves screenshots, so the result can be
attached to the acceptance record. The API and Worker must already be running (loopback only)
and the page is served by the research API itself, so this also checks the single-entry claim.

    python scripts/browser-acceptance.py --material fixtures/research/story.txt
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from websockets.sync.client import connect

EDGE_CANDIDATES = [
    r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
]


class Browser:
    def __init__(self, url: str, port: int, profile: Path):
        self.url, self.port, self.profile = url, port, profile
        self.process = None
        self.ws = None
        self.counter = 0

    # ------------------------------------------------------------------ transport
    def probe(self):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{self.port}/json/version', timeout=2) as r:
                return json.loads(r.read())
        except OSError:
            return None

    def start(self, launch=True):
        existing = self.probe()
        if existing:
            print(f'using the browser already listening on {self.port} ({existing.get("Browser")})')
            return
        if not launch:
            raise SystemExit(f'No browser on port {self.port}; start one or allow the script to launch it.')
        exe = next((p for p in EDGE_CANDIDATES if Path(p).exists()), None)
        if not exe:
            raise SystemExit('Microsoft Edge not found; install a Chromium browser to run this check.')
        self.profile.mkdir(parents=True, exist_ok=True)
        stderr = open(self.profile.parent / 'edge.stderr.log', 'wb')
        self.process = subprocess.Popen([exe, '--headless=new', f'--remote-debugging-port={self.port}',
            f'--user-data-dir={self.profile}', '--no-first-run', '--no-default-browser-check',
            '--disable-gpu', '--window-size=1440,900', 'about:blank'],
            stdout=subprocess.DEVNULL, stderr=stderr)
        deadline = time.time() + 60
        while time.time() < deadline:
            if self.probe():
                return
            time.sleep(0.4)
        raise SystemExit(f'Headless browser did not expose the debugging port; see {stderr.name}')

    def page(self, url: str):
        request = urllib.request.Request(f'http://127.0.0.1:{self.port}/json/new?{url}', method='PUT')
        with urllib.request.urlopen(request, timeout=30) as r:
            target = json.loads(r.read())
        self.ws = connect(target['webSocketDebuggerUrl'], max_size=80 * 1024 * 1024)
        self.send('Page.enable')
        self.send('Runtime.enable')
        self.send('DOM.enable')
        return self

    def send(self, method, **params):
        self.counter += 1
        self.ws.send(json.dumps({'id': self.counter, 'method': method, 'params': params}))
        while True:
            message = json.loads(self.ws.recv())
            if message.get('id') == self.counter:
                if 'error' in message:
                    raise RuntimeError(f'{method}: {message["error"]}')
                return message.get('result', {})

    def js(self, expression, timeout=30):
        wrapped = ('(async () => {' + expression + '})()')
        result = self.send('Runtime.evaluate', expression=wrapped, awaitPromise=True,
                           returnByValue=True, timeout=timeout * 1000)
        if result.get('exceptionDetails'):
            raise RuntimeError(f'page error: {result["exceptionDetails"].get("text")} '
                               f'{result.get("exceptionDetails", {}).get("exception", {}).get("description", "")}')
        return result.get('result', {}).get('value')

    def wait(self, predicate, timeout=30, label=''):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if self.js(f'return !!({predicate});', timeout=10):
                    return True
            except RuntimeError:
                pass
            time.sleep(0.4)
        return False

    def require(self, predicate, timeout=30, label=''):
        if not self.wait(predicate, timeout, label):
            raise TimeoutError(f'timed out waiting for {label or predicate}')

    def wait_value(self, selector, needle, timeout=30, label=''):
        return self.wait(
            f'(document.querySelector({json.dumps(selector)})||{{}}).value?.includes({json.dumps(needle)})',
            timeout, label or f'{selector} to contain {needle!r}')

    def text(self):
        return self.js('return document.body.innerText;')

    def screenshot(self, path: Path):
        data = self.send('Page.captureScreenshot', format='png')['data']
        path.write_bytes(base64.b64decode(data))

    def set_files(self, selector, files):
        root = self.send('DOM.getDocument', depth=-1)['root']['nodeId']
        node = self.send('DOM.querySelector', nodeId=root, selector=selector)['nodeId']
        if not node:
            raise RuntimeError(f'file input not found: {selector}')
        self.send('DOM.setFileInputFiles', files=[str(f) for f in files], nodeId=node)

    def close(self):
        try:
            if self.ws:
                self.ws.close()
        finally:
            if self.process:
                self.process.terminate()


CHECKS = []


def check(name, ok, detail=''):
    CHECKS.append({'check': name, 'ok': bool(ok), 'detail': str(detail)[:400]})
    print(('PASS ' if ok else 'FAIL ') + name + (f' :: {detail}' if detail else ''))


def click_text(browser, selector, text, starts=False):
    """Click the first element matching selector whose text contains (or starts with) text."""
    match = 'startsWith' if starts else 'includes'
    return browser.js(f"""
      const nodes=[...document.querySelectorAll({json.dumps(selector)})];
      const node=nodes.find(n=>n.textContent && n.textContent.trim().{match}({json.dumps(text)}));
      if(!node) return false;
      node.scrollIntoView({{block:'center'}}); node.click(); return true;""")


def set_value(browser, selector, value):
    return browser.js(f"""
      const node=document.querySelector({json.dumps(selector)});
      if(!node) return false;
      const proto=node.tagName==='TEXTAREA'?window.HTMLTextAreaElement.prototype:
        node.tagName==='SELECT'?window.HTMLSelectElement.prototype:window.HTMLInputElement.prototype;
      const setter=Object.getOwnPropertyDescriptor(proto,'value').set;
      setter.call(node,{json.dumps(value)});
      node.dispatchEvent(new Event('input',{{bubbles:true}}));
      node.dispatchEvent(new Event('change',{{bubbles:true}}));
      return true;""")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:8010')
    parser.add_argument('--port', type=int, default=9333)
    parser.add_argument('--material', required=True)
    parser.add_argument('--out', default='output/acceptance-browser')
    parser.add_argument('--no-launch', action='store_true', help='reuse a browser already on --port')
    parser.add_argument('--project', default='验收项目 A')
    parser.add_argument('--quote', default='')
    parser.add_argument('--question', default='这段材料中“自由”的使用有什么前提？')
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    material = Path(args.material).resolve()
    browser = Browser(args.base_url, args.port, out / 'edge-profile')
    try:
        browser.start(launch=not args.no_launch)
        browser.page('about:blank')
        browser.send('Page.navigate', url=args.base_url + '/')
        browser.require(f"location.origin==={json.dumps(args.base_url)}", 60, 'origin')
        browser.require("document.readyState==='complete'", 60, 'initial load')
        # Accept the app's own one-session brand animation as already shown, without touching flow.
        browser.js("""
          sessionStorage.setItem('hermeneut_brand_seen','1');
          localStorage.setItem('hermeneut_startup_config', JSON.stringify({enabled:false}));
          localStorage.setItem('hermeneut_research_url', location.origin);""")
        browser.send('Page.reload')
        browser.require("!!document.querySelector('.unified-workspace')", 90, 'workspace render')
        check('UI-01 统一入口加载研究工作台', True, browser.js('return document.title'))

        # Prompt-free project creation: the UI uses prompt() for the project name.
        browser.js(f"window.prompt=()=>{json.dumps(args.project)}; window.confirm=()=>true;")
        click_text(browser, '.uw-sidebar button', '＋ 项目')
        browser.require(f"[...document.querySelectorAll('.uw-sidebar option')].some(o=>o.textContent==={json.dumps(args.project)})",
                        30, 'project option')
        click_text(browser, '.uw-sidebar button', '＋ 新研究')
        browser.require("!!document.querySelector('.uw-conversation-header h1')", 30, 'conversation header')
        check('UI-01 同页创建项目与会话', True, browser.js(
            "return document.querySelector('.uw-conversation-header h1').textContent;"))

        # Import material through the composer attachment input (same single service).
        browser.set_files('form.uw-composer input[type=file]', [material])
        browser.require("!!document.querySelector('.uw-material')", 60, 'material listed')
        processed = browser.wait("[...document.querySelectorAll('.uw-material button')].some(b=>b.textContent.includes('可阅读'))",
                                 150, 'material processed')
        check('MAT-01 导入材料并被后台任务处理', processed, browser.js(
            "return [...document.querySelectorAll('.uw-material button')].map(b=>b.textContent).join(' | ');"))

        click_text(browser, '.uw-material button', '')
        browser.require("!!document.querySelector('.uw-source p[data-source]')", 60, 'reader segments')
        check('MAT-01 原文可阅读', True, browser.js(
            "return document.querySelectorAll('.uw-source p[data-source]').length + ' segments';"))

        # Select text inside the first immutable segment and save a note with its anchor.
        selected = browser.js("""
          const p=document.querySelector('.uw-source p[data-source]');
          const text=p.textContent||'';
          const node=p.firstChild;
          const length=Math.min(12,text.length);
          if(!node||length<2) return '';
          const range=document.createRange();
          range.setStart(node,0); range.setEnd(node,length);
          const selection=window.getSelection();
          selection.removeAllRanges(); selection.addRange(range);
          document.dispatchEvent(new Event('selectionchange'));
          return selection.toString();""")
        browser.require("!!document.querySelector('.uw-selection blockquote')", 30, 'selection captured')
        set_value(browser, '.uw-selection textarea', '验收笔记：先记录当前理解。')
        click_text(browser, '.uw-selection button', '保存笔记与证据')
        browser.require("!!document.querySelector('.uw-artifact-content')", 60, 'note artifact opened')
        note = browser.js("return document.querySelector('.uw-artifact-content').innerText.slice(0,160);")
        check('MAT-02 选区一次保存笔记与证据锚点', bool(selected) and '验收笔记' in note,
              selected + ' | ' + (note or '').replace('\n', ' '))
        browser.screenshot(out / '02-note-and-evidence.png')

        # Jump back from the artifact to the exact highlight in the original text.
        click_text(browser, '.uw-artifact-content button', '原文 1')
        browser.require("!!document.querySelector('.uw-source mark')", 60, 'highlight')
        check('MAT-03 从证据回跳原文并高亮', True, browser.js(
            "return (document.querySelector('.uw-source mark')||{}).textContent;"))
        browser.screenshot(out / '03-evidence-locate.png')

        # Draft survives a reload without sending (UI-02/UI-04 state separation).
        set_value(browser, 'form.uw-composer textarea', '未发送的草稿：先不提交。')
        stored = browser.wait("[...Object.keys(localStorage)].filter(k=>k.startsWith('hermeneut_draft:')).some(k=>localStorage.getItem(k).includes('未发送的草稿'))",
                              15, 'draft persisted locally')
        browser.send('Page.reload')
        restored = browser.wait_value('form.uw-composer textarea', '未发送的草稿', 40,
                                      'composer draft restored after reload')
        check('UI-02 刷新后未发送输入保留', stored and restored, browser.js(
            "const t=document.querySelector('form.uw-composer textarea'); return t?t.value:'missing';"))
        browser.screenshot(out / '04-draft-restored.png')

        # Ask a question in demo mode: no provider key, no silent "success" claim.
        browser.require("!!document.querySelector('form.uw-composer textarea')", 60, 'composer ready')
        click_text(browser, '.uw-composer-toolbar button', '选项')
        browser.require("!!document.querySelector('.uw-advanced select')", 20, 'advanced options')
        set_value(browser, '.uw-advanced select', 'demo')
        browser.require("document.querySelector('.uw-advanced select').value==='demo'", 20, 'demo mode')
        set_value(browser, 'form.uw-composer textarea', args.question)
        ready = browser.wait(f"document.querySelector('form.uw-composer textarea').value==={json.dumps(args.question)}"
                             "&& ![...document.querySelectorAll('.uw-composer button')].find(b=>b.textContent.includes('发送')).disabled",
                             20, 'composer ready to send')
        check('RES-01 演示模式可提交问题', ready, args.question)
        click_text(browser, '.uw-composer button', '发送')
        replied = browser.wait("[...document.querySelectorAll('.uw-message.assistant')].some(m=>m.textContent.includes('演示'))",
                               150, 'assistant reply')
        check('RES-01 会话内呈现结果与演示标记', replied, browser.js(
            "return [...document.querySelectorAll('.uw-message.assistant')].map(m=>m.innerText.slice(0,80)).join(' / ');"))
        browser.screenshot(out / '05-demo-reply.png')

        # Version comparison must not pretend to work with a single text version (MAT-04).
        if not browser.js("return !!document.querySelector('.uw-material')"):
            click_text(browser, '.uw-sidebar button', '材料', starts=True)
            browser.require("!!document.querySelector('.uw-material')", 30, 'material library opened')
        click_text(browser, '.uw-material button', '')
        browser.require("!!document.querySelector('.uw-source')", 60, 'reader again')
        disabled = browser.js("""
          const b=[...document.querySelectorAll('.uw-document-body button')].find(x=>x.textContent.includes('比较上一版'));
          return b ? b.disabled : 'missing';""")
        check('MAT-04 单版本时不做虚假版本对照', disabled is True, f'button disabled={disabled}')

        # Upload a researcher revision and compare the two versions segment by segment (MAT-04).
        revision = browser.js("""
          const base=location.origin + '/api/v2/projects/' +
            encodeURIComponent(localStorage.getItem('hermeneut_research_project'));
          const materials=await (await fetch(base + '/materials')).json();
          const material=materials[0];
          const tei=await (await fetch(base + '/materials/' + material.id + '/tei')).text();
          const revised=tei.replace(/(<p xml:id="[^"]*">)([^<]{1,40})/, '$1修订后的第一段。');
          const response=await fetch(base + '/materials/' + material.id + '/revisions', {method:'POST',
            headers:{'Content-Type':'application/json'}, body: JSON.stringify({revision: material.revision, tei: revised})});
          return [response.status, (await response.text()).slice(0,80), material.revision];""")
        check('MAT-04 上传修订产生新文本版本', revision[0] in (200, 201), revision)
        enabled = browser.wait("""(() => {
          const b=[...document.querySelectorAll('.uw-document-body button')].find(x=>x.textContent.includes('比较上一版'));
          return !!b && !b.disabled;
        })()""", 40, 'compare button enabled after revision')
        if enabled:
            click_text(browser, '.uw-document-body button', '比较上一版')
        compared = browser.wait("!!document.querySelector('.uw-version-diff')", 40, 'version comparison')
        detail = browser.js("return (document.querySelector('.uw-version-diff')||{}).innerText||'';")
        check('MAT-04 两版本逐段对照可读', enabled and compared and '文本修改' in detail,
              (detail or '').replace('\n', ' ')[:160])
        browser.screenshot(out / '07-version-compare.png')

        # Narrow screen: document replaces the conversation, then returns without losing input.
        browser.send('Emulation.setDeviceMetricsOverride', width=480, height=860, deviceScaleFactor=1, mobile=False)
        time.sleep(0.6)
        state = browser.js("""
          const doc=document.querySelector('.uw-document-pane');
          const conv=document.querySelector('.uw-conversation');
          return {doc: doc?getComputedStyle(doc).display:'missing', conv: conv?getComputedStyle(conv).display:'missing'};""")
        check('UI-05 窄屏只显示一个长区域', state['conv'] == 'none' and state['doc'] != 'none', json.dumps(state))
        browser.screenshot(out / '08-narrow-document.png')
        browser.js("document.querySelector('.uw-document-pane header button').click();")
        returned = browser.wait("getComputedStyle(document.querySelector('.uw-conversation')).display!=='none'", 20,
                                'conversation back')
        check('UI-05 返回对话后输入区仍在', returned, browser.js(
            "return document.querySelector('form.uw-composer textarea')?.value;"))
        browser.send('Emulation.clearDeviceMetricsOverride')

        # Second project must not inherit the first project's messages or materials (UI-03).
        browser.js(f"window.prompt=()=>{json.dumps(args.project + ' B')};")
        click_text(browser, '.uw-sidebar button', '＋ 项目')
        browser.require("!!document.querySelector('.uw-welcome')", 60, 'empty project')
        empty = browser.js("""
          return {messages: document.querySelectorAll('.uw-message').length,
                  materials: document.querySelectorAll('.uw-material').length,
                  welcome: !!document.querySelector('.uw-welcome')};""")
        check('UI-03 切换项目不串消息与材料',
              empty['messages'] == 0 and empty['materials'] == 0 and empty['welcome'], json.dumps(empty))
        browser.screenshot(out / '09-second-project.png')

        browser.js(f"""
          const select=document.querySelector('.uw-sidebar select');
          const option=[...select.options].find(o=>o.textContent==={json.dumps(args.project)});
          const setter=Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype,'value').set;
          setter.call(select, option.value);
          select.dispatchEvent(new Event('change',{{bubbles:true}}));""")
        browser.require("[...document.querySelectorAll('.uw-session-list button')].length>0", 60, 'project switch back')
        browser.js("document.querySelector('.uw-session-list button').click();")
        restored_messages = browser.wait("[...document.querySelectorAll('.uw-message')].length>0", 60, 'messages restored')
        check('UI-03 返回原项目消息恢复', restored_messages, browser.js(
            "return document.querySelectorAll('.uw-message').length + ' messages';"))
        browser.screenshot(out / '10-project-restored.png')

        # Export through the single document area (WRITE-01 partial: saved version consistency).
        exported = browser.js("""
          const r=await fetch(location.origin + '/api/v2/projects/' +
            encodeURIComponent(localStorage.getItem('hermeneut_research_project')) + '/export?format=md');
          const text=await r.text();
          return [r.status, text.length, text.slice(0,80)];""")
        check('WRITE-01 项目导出可用', exported[0] == 200 and exported[1] > 0, exported)
    finally:
        browser.close()

    report = {'checks': CHECKS, 'passed': sum(1 for c in CHECKS if c['ok']), 'total': len(CHECKS)}
    (out / 'browser-acceptance.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'total': report['total']}, ensure_ascii=False))
    return 0 if report['passed'] == report['total'] else 1


if __name__ == '__main__':
    sys.exit(main())
