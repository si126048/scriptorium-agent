import { useRef, useEffect, useCallback } from 'react';
import { LOGO_PATH } from './LogoSVG';
import { DEFAULT_CONFIG, STEPS as ORIGINAL_STEPS, loadConfig, shouldPlay } from './startupConfig';
import type { StartupConfig, StartupStep } from './startupConfig';
import './startup.css';

interface Props {
  onComplete: () => void;
  brandingOnly?: boolean;
}

function clamp01(v: number, lo = 0, hi = 1): number {
  const n = Number(v);
  return isFinite(n) ? Math.min(hi, Math.max(lo, n)) : lo;
}

export function StartupAnimation({ onComplete, brandingOnly = false }: Props) {
  const rootRef = useRef<HTMLDivElement>(null);
  const completedRef = useRef(false);

  const finish = useCallback(() => {
    if (completedRef.current) return;
    completedRef.current = true;
    const root = rootRef.current;
    if (!root) return;
    root.classList.add('ha-handoff');
    setTimeout(() => {
      root.classList.add('ha-gone');
      setTimeout(onComplete, 700);
    }, 780);
  }, [onComplete]);

  useEffect(() => {
    const rootEl = rootRef.current;
    if (!rootEl) return;
    const root: HTMLDivElement = rootEl;

    const C: StartupConfig = { ...DEFAULT_CONFIG, ...loadConfig() };
    const STEPS = brandingOnly ? ORIGINAL_STEPS.map((step, index) => ({ ...step,
      zh: ['打开研究项目', '准备材料阅读', '连接研究会话', '恢复工作位置', '准备就绪'][index % 5],
      en: 'RESEARCH WORKSPACE', say: 'Preparing research workspace.',
      log: '正在准备工作台', logEn: 'PREPARING WORKSPACE',
      action: step.action === 'auto' ? 'auto' as const : 'confirm' as const,
      btnZh: '继续', btnEn: 'CONTINUE',
    })) : ORIGINAL_STEPS;
    C.speed = clamp01(C.speed, 0.35, 3);
    C.identity = String(C.identity || 'OPERATOR').slice(0, 48);

    if (!C.enabled || !shouldPlay(C.mode)) {
      finish();
      return;
    }

    const ms = (base: number) => Math.round(base / C.speed);
    const timers: number[] = [];
    const waiters: Array<() => void> = [];
    let skipped = false;
    let finished = false;
    let hexTimer: ReturnType<typeof setInterval> | null = null;
    let clockTimer: ReturnType<typeof setInterval> | null = null;

    function wait(base: number): Promise<void> {
      return new Promise((resolve) => {
        if (skipped) return resolve();
        let done = false;
        function fin() {
          if (done) return;
          done = true;
          const i = waiters.indexOf(fin);
          if (i >= 0) waiters.splice(i, 1);
          resolve();
        }
        const t = setTimeout(fin, Math.max(0, ms(base)));
        timers.push(t);
        waiters.push(fin);
      });
    }

    function waitAction(): Promise<void> {
      return new Promise((resolve) => {
        if (skipped || !C.requireInteraction) return resolve();
        let done = false;
        function fin() {
          if (done) return;
          done = true;
          cleanup();
          resolve();
        }
        function onKey(e: KeyboardEvent) {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fin(); }
        }
        function onClick(e: MouseEvent) { e.preventDefault(); fin(); }
        function cleanup() {
          btn.removeEventListener('click', onClick);
          actionEl.removeEventListener('click', onClick);
          document.removeEventListener('keydown', onKey);
          const i = waiters.indexOf(fin);
          if (i >= 0) waiters.splice(i, 1);
        }
        btn.addEventListener('click', onClick);
        actionEl.addEventListener('click', onClick);
        document.addEventListener('keydown', onKey);
        waiters.push(fin);
      });
    }

    function releaseAll() {
      for (const t of timers) clearTimeout(t);
      timers.length = 0;
      const list = waiters.slice();
      waiters.length = 0;
      for (const fn of list) { try { fn(); } catch { /* noop */ } }
    }

    function q(sel: string): HTMLElement { return root.querySelector(sel)!; }

    function typeIn(host: HTMLElement, text: string, stagger: number) {
      host.textContent = '';
      const frag = document.createDocumentFragment();
      let n = 0;
      for (let i = 0; i < text.length; i++) {
        const ch = text.charAt(i);
        if (ch === ' ') { frag.appendChild(document.createTextNode('\u00a0')); continue; }
        const s = document.createElement('span');
        s.className = 'ha-ch';
        s.textContent = ch;
        s.style.transitionDelay = Math.round(n * stagger) + 'ms';
        frag.appendChild(s);
        n++;
      }
      host.appendChild(frag);
    }

    /* ── DOM 搭建 ─────────────────────────────────────────────── */
    root.classList.toggle('ha-dark', C.theme === 'dark');
    root.style.setProperty('--ha-speed', String(C.speed));
    root.style.setProperty('--ha-accent', C.accent);
    root.style.setProperty('--ha-glitch-a', C.glitchA);
    root.style.setProperty('--ha-glitch-b', C.glitchB);

    root.innerHTML = `
      <div class="ha-plate"></div>
      <div class="ha-vignette"></div>
      <div class="ha-watermark"></div>
      <div class="ha-grain"></div>
      <div class="ha-black"><div class="ha-black-inner"></div><div class="ha-sweep"></div></div>
      <div class="ha-wash"></div>
      <header class="ha-brand">
        <div class="ha-brand-1"></div><div class="ha-brand-2"></div>
        <div class="ha-brand-3"><b></b><span></span></div>
      </header>
      <div class="ha-stepcount">[ 00 / 06 ] INIT</div>
      <div class="ha-center">
        <div class="ha-status"><span class="ha-status-zh"></span><i class="ha-caret"></i></div>
        <div class="ha-sub-en"></div>
        <div class="ha-rule"></div>
        <div class="ha-logo"></div>
        <div class="ha-dots" hidden></div>
      </div>
      <div class="ha-idline"></div>
      <div class="ha-reticle"></div>
      <div class="ha-hex"></div>
      <div class="ha-welcome">
        <div class="ha-w1">WELCOME TO</div>
        <div class="ha-w2"></div>
        <div class="ha-w3"></div>
        <div class="ha-w4"></div>
      </div>
      <div class="ha-action">
        <div class="ha-card" hidden></div>
        <button class="ha-btn" type="button">
          <span class="ha-btn-zh"></span><span class="ha-btn-en"></span>
        </button>
        <div class="ha-hint"></div>
      </div>
      <div class="ha-frame">
        <i class="ha-corner ha-c-tl"></i><i class="ha-corner ha-c-tr"></i>
        <i class="ha-corner ha-c-bl"></i><i class="ha-corner ha-c-br"></i>
        <div class="ha-scanline"></div>
      </div>
      <div class="ha-slats"></div>
      <div class="ha-voice"><i></i><i></i><i></i><i></i><i></i></div>
      <div class="ha-meta"><span class="ha-meta-1"></span><span class="ha-meta-2"></span></div>
      <div class="ha-skip">SKIP ▸</div>
      <footer class="ha-foot"><span></span><i></i></footer>
      <div class="ha-subtitle"><span class="ha-sub-zh"></span><span class="ha-sub-en2"></span></div>
      <div class="ha-progress"><i></i></div>
      <div class="ha-bloom"></div>
      <div class="ha-streak"></div>
      <div class="ha-flash"></div>`;

    /* ── 元素引用 ─────────────────────────────────────────────── */
    const plate = q('.ha-plate');
    const watermark = q('.ha-watermark');
    const black = q('.ha-black');
    const blackInner = q('.ha-black-inner');
    const sweepEl = q('.ha-sweep');
    const wash = q('.ha-wash');
    const flash = q('.ha-flash');
    const bloom = q('.ha-bloom');
    const streak = q('.ha-streak');
    const vignette = q('.ha-vignette');
    const brand = q('.ha-brand');
    const center = q('.ha-center');
    const brand1 = q('.ha-brand-1');
    const brand2 = q('.ha-brand-2');
    const brand3b = q('.ha-brand-3 b');
    const brand3s = q('.ha-brand-3 span');
    const stepcount = q('.ha-stepcount');
    const status = q('.ha-status');
    const statusZh = q('.ha-status-zh');
    const caret = q('.ha-caret');
    const subEn = q('.ha-sub-en');
    const rule = q('.ha-rule');
    const logo = q('.ha-logo');
    const dots = q('.ha-dots');
    const idline = q('.ha-idline');
    const reticle = q('.ha-reticle');
    const hex = q('.ha-hex');
    const welcome = q('.ha-welcome');
    const w1 = q('.ha-w1');
    const w2 = q('.ha-w2');
    const w3 = q('.ha-w3');
    const w4 = q('.ha-w4');
    const actionEl = q('.ha-action');
    const card = q('.ha-card');
    const btn = q('.ha-btn') as HTMLButtonElement;
    const btnZh = q('.ha-btn-zh');
    const btnEn = q('.ha-btn-en');
    const hint = q('.ha-hint');
    const skipBtn = q('.ha-skip');
    const foot = q('.ha-foot');
    const footText = q('.ha-foot span');
    const subZh = q('.ha-sub-zh');
    const subEn2 = q('.ha-sub-en2');
    const bar = q('.ha-progress i');
    const frame = q('.ha-frame');
    const scanline = q('.ha-scanline');
    const slats = q('.ha-slats');
    const voice = q('.ha-voice');
    const meta = q('.ha-meta');
    const meta1 = q('.ha-meta-1');
    const meta2 = q('.ha-meta-2');

    /* ── 内容填充 ─────────────────────────────────────────────── */
    brand1.textContent = C.brand1;
    brand2.textContent = C.brand2;
    brand3b.textContent = C.brand3a;
    brand3s.textContent = C.brand3b;
    footText.textContent = C.footer;
    w2.textContent = C.welcomeBox;
    w4.textContent = '欢迎 ' + C.identity + ' 访问';
    idline.textContent = '· ID CONFIRMED : ' + C.identity.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 12).padEnd(4, '0');

    /* ── 黑幕标识 ─────────────────────────────────────────────── */
    const whaleSvg = `<svg viewBox="0 0 50 50" class="ha-whale" aria-hidden="true"><path d="${LOGO_PATH}" fill-rule="evenodd" fill="currentColor"/></svg>`;
    blackInner.innerHTML = whaleSvg +
      `<div class="ha-black-zh">${C.orgZh}</div>` +
      `<div class="ha-black-en">${C.orgEn}</div>` +
      `<div class="ha-black-sub">${C.orgSub}</div>`;
    const blackEn = q('.ha-black-en');

    /* ── Logo 区 ─────────────────────────────────────────────── */
    logo.innerHTML = `<svg viewBox="0 0 50 50" aria-hidden="true"><path d="${LOGO_PATH}" fill-rule="evenodd" fill="currentColor"/></svg>` +
      '<div class="ha-logolabel">H E R M E N E U T</div>';
    w3.innerHTML = `<svg viewBox="0 0 50 50" aria-hidden="true"><path d="${LOGO_PATH}" fill-rule="evenodd" fill="currentColor"/></svg>` +
      '<span>H E R M E N E U T · A G E N T</span>';

    /* ── 水印面板 ─────────────────────────────────────────────── */
    const boxes = [[0.60, 0.02, 0.16, 0.96], [0.78, 0.02, 0.16, 0.96], [0.96, 0.02, 0.16, 0.96], [0.05, 0.02, 0.10, 0.5]];
    for (const b of boxes) {
      const n = document.createElement('div');
      n.className = 'ha-wm';
      n.style.cssText = `left:${b[0]*100}%;top:${b[1]*100}%;width:${b[2]*100}%;height:${b[3]*100}%`;
      watermark.appendChild(n);
    }

    /* ── 阶段格 + 时钟 ────────────────────────────────────────── */
    for (let i = 0; i < STEPS.length + 1; i++) slats.appendChild(document.createElement('i'));
    (slats.querySelectorAll('.ha-slat') as NodeListOf<HTMLElement>).forEach(el => el.className = 'ha-slat');
    meta1.textContent = 'REV 3.1.0 · WEB PROFILE';
    function paintClock() {
      const d = new Date();
      const p = (n: number) => (n < 10 ? '0' : '') + n;
      meta2.textContent = p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds());
    }
    paintClock();
    clockTimer = setInterval(paintClock, 1000);

    /* ── 环形准星 SVG ─────────────────────────────────────────── */
    (function buildReticle() {
      const ns = 'http://www.w3.org/2000/svg';
      const svg = document.createElementNS(ns, 'svg');
      svg.setAttribute('viewBox', '0 0 400 400');
      function arc(cx: number, cy: number, r: number, a0: number, a1: number, cls: string, cap?: string) {
        const rad = (d: number) => (d - 90) * Math.PI / 180;
        const x0 = cx + r * Math.cos(rad(a0)), y0 = cy + r * Math.sin(rad(a0));
        const x1 = cx + r * Math.cos(rad(a1)), y1 = cy + r * Math.sin(rad(a1));
        const large = (a1 - a0) > 180 ? 1 : 0;
        const p = document.createElementNS(ns, 'path');
        p.setAttribute('d', `M${x0.toFixed(2)} ${y0.toFixed(2)} A${r} ${r} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`);
        p.setAttribute('class', cls);
        if (cap) p.setAttribute('stroke-linecap', cap);
        return { node: p, x: x1, y: y1, x0, y0 };
      }
      const gA = document.createElementNS(ns, 'g');
      gA.setAttribute('class', 'ha-ret-rot-a');
      const a = arc(200, 200, 150, 215, 505, 'ha-ring-a', 'round');
      gA.appendChild(a.node);
      const da = document.createElementNS(ns, 'circle');
      da.setAttribute('class', 'ha-dot-a');
      da.setAttribute('cx', a.x.toFixed(2)); da.setAttribute('cy', a.y.toFixed(2)); da.setAttribute('r', '7');
      gA.appendChild(da);
      svg.appendChild(gA);
      const gB = document.createElementNS(ns, 'g');
      gB.setAttribute('class', 'ha-ret-rot-b');
      const b = arc(200, 200, 104, 200, 490, 'ha-ring-b', 'round');
      gB.appendChild(b.node);
      const db = document.createElementNS(ns, 'circle');
      db.setAttribute('class', 'ha-dot-b');
      db.setAttribute('cx', b.x0.toFixed(2)); db.setAttribute('cy', b.y0.toFixed(2)); db.setAttribute('r', '4');
      gB.appendChild(db);
      svg.appendChild(gB);
      const gC = document.createElementNS(ns, 'g');
      gC.appendChild(arc(200, 200, 62, 118, 242, 'ha-bracket', 'round').node);
      gC.appendChild(arc(200, 200, 62, 298, 62, 'ha-bracket', 'round').node);
      svg.appendChild(gC);
      for (const pt of [[152, 132], [252, 268], [278, 150]]) {
        const c = document.createElementNS(ns, 'circle');
        c.setAttribute('class', 'ha-dot-o');
        c.setAttribute('cx', String(pt[0])); c.setAttribute('cy', String(pt[1])); c.setAttribute('r', '2.8');
        svg.appendChild(c);
      }
      reticle.appendChild(svg);
    })();

    /* ── 音频引擎 ─────────────────────────────────────────────── */
    let audioCtx: AudioContext | null = null;
    function ac(force?: boolean): AudioContext | null {
      if (!C.sound && !force) return null;
      try {
        const AC = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
        if (!AC) return null;
        if (!audioCtx) audioCtx = new AC();
        if (audioCtx.state === 'suspended' && typeof audioCtx.resume === 'function') audioCtx.resume();
        return audioCtx;
      } catch { return null; }
    }
    function vol(gain: number) { return Math.max(0.0002, (gain ?? 0.05) * clamp01(C.soundVolume) * 2); }
    function tone(freq: number, dur: number, type: OscillatorType, gain: number, delay = 0, glideTo?: number) {
      const c = ac(); if (!c) return;
      try {
        const t0 = c.currentTime + delay;
        const o = c.createOscillator(), g = c.createGain();
        o.type = type; o.frequency.setValueAtTime(freq, t0);
        if (glideTo) o.frequency.exponentialRampToValueAtTime(glideTo, t0 + dur);
        g.gain.setValueAtTime(0.0001, t0);
        g.gain.exponentialRampToValueAtTime(vol(gain), t0 + Math.min(0.02, dur * 0.3));
        g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
        o.connect(g); g.connect(c.destination);
        o.start(t0); o.stop(t0 + dur + 0.03);
      } catch { /* noop */ }
    }
    function noise(dur: number, gain: number) {
      const c = ac(); if (!c) return;
      try {
        const n = Math.floor(c.sampleRate * dur);
        const buf = c.createBuffer(1, n, c.sampleRate);
        const d = buf.getChannelData(0);
        for (let i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / n);
        const src = c.createBufferSource(); src.buffer = buf;
        const f = c.createBiquadFilter(); f.type = 'bandpass'; f.frequency.value = 1500; f.Q.value = 0.6;
        const g = c.createGain(); g.gain.value = vol(gain);
        src.connect(f); f.connect(g); g.connect(c.destination);
        src.start();
      } catch { /* noop */ }
    }
    const audio = {
      tick: () => tone(1760, 0.035, 'square', 0.022),
      confirm: () => { tone(660, 0.09, 'triangle', 0.07); tone(990, 0.17, 'triangle', 0.055, 0.085); },
      step: () => { tone(880, 0.05, 'sine', 0.05); tone(1320, 0.07, 'sine', 0.028, 0.045); },
      sweep: () => noise(0.75, 0.035),
      cue: () => { tone(1046.5, 0.05, 'sine', 0.028); tone(1568, 0.06, 'sine', 0.02, 0.075); },
      rise: () => tone(220, 1.1, 'sine', 0.032, 0, 990),
      chime: () => { tone(659.25, 0.9, 'sine', 0.055); tone(830.61, 0.9, 'sine', 0.04, 0.09); tone(987.77, 1.3, 'sine', 0.045, 0.18); },
    };

    /* ── 语音引擎 ─────────────────────────────────────────────── */
    const speechSupported = typeof window !== 'undefined' && !!window.speechSynthesis;
    let voices: SpeechSynthesisVoice[] = [];
    let pickedVoice: SpeechSynthesisVoice | null = null;
    let saidOnce = false;

    const FEMALE_HINTS = ['aria','jenny','michelle','emma','ava','libby','sonia','maisie','zira','samantha','karen','moira','tessa','victoria','serena','allison','susan','fiona','hazel','female','woman','xiaoxiao','xiaoyi','xiaomo','huihui','yaoyao','晓晓','晓伊','女声'];
    const NATURAL_HINTS = ['natural','neural','online','premium','enhanced','siri','google'];
    const MALE_HINTS = ['david','mark','guy','ryan','george','daniel','alex','fred','male','yunxi','yunjian','kangkang'];

    function scoreVoice(v: SpeechSynthesisVoice): number {
      const n = v.name.toLowerCase(), l = v.lang.toLowerCase();
      let sc = 0;
      for (const h of NATURAL_HINTS) if (n.includes(h)) { sc += 60; break; }
      for (const h of FEMALE_HINTS) if (n.includes(h)) { sc += 40; break; }
      for (const h of MALE_HINTS) if (n.includes(h)) { sc -= 45; break; }
      if (l.startsWith('en')) sc += 25;
      if (v.localService) sc += 4;
      if (v.default) sc += 3;
      return sc;
    }

    function loadVoices() {
      if (!speechSupported) return;
      try { voices = window.speechSynthesis.getVoices() || []; } catch { voices = []; }
      const pool = voices.filter(v => v.lang.toLowerCase().startsWith('en'));
      const candidates = pool.length ? pool : voices;
      let best: SpeechSynthesisVoice | null = null;
      let bs = -1e9;
      for (const v of candidates) { const sc = scoreVoice(v); if (sc > bs) { bs = sc; best = v; } }
      pickedVoice = best;
    }
    loadVoices();
    if (speechSupported && typeof window.speechSynthesis.addEventListener === 'function') {
      try { window.speechSynthesis.addEventListener('voiceschanged', loadVoices); } catch { /* noop */ }
    }

    function speakLine(text: string): Promise<number> {
      return new Promise((resolve) => {
        if (!speechSupported || !C.voice || finished) { resolve(0); return; }
        const u = new SpeechSynthesisUtterance(text);
        if (pickedVoice) { u.voice = pickedVoice; u.lang = pickedVoice.lang; } else u.lang = 'en-US';
        u.rate = clamp01(C.voiceRate, 0.5, 2);
        u.pitch = clamp01(C.voicePitch, 0, 2);
        u.volume = clamp01(C.voiceVolume, 0, 1);
        const startedAt = Date.now();
        u.onstart = () => voice.classList.add('ha-on');
        u.onend = () => { voice.classList.remove('ha-on'); resolve(Date.now() - startedAt); };
        u.onerror = () => { voice.classList.remove('ha-on'); resolve(0); };
        saidOnce = true;
        if (C.voiceCue) audio.cue();
        setTimeout(() => {
          if (finished) { resolve(0); return; }
          try { window.speechSynthesis.speak(u); } catch { resolve(0); }
        }, clamp01(C.voiceLead, 0, 1200));
      });
    }

    function stopVoice() { try { if (speechSupported) window.speechSynthesis.cancel(); } catch { /* noop */ } voice.classList.remove('ha-on'); }

    /* ── 工具函数 ─────────────────────────────────────────────── */
    function setProgress(p: number) { bar.style.width = Math.round(clamp01(p) * 100) + '%'; }

    function setSlats(active: number) {
      const items = slats.children;
      for (let i = 0; i < items.length; i++) {
        const idx = i + 1;
        (items[i] as HTMLElement).classList.toggle('ha-on', idx === active);
        (items[i] as HTMLElement).classList.toggle('ha-past', idx < active);
      }
    }

    function sweep() {
      scanline.classList.remove('ha-go');
      void scanline.offsetWidth;
      scanline.classList.add('ha-go');
    }

    function setSubtitle(zh: string, en: string) {
      subZh.classList.remove('ha-in');
      subEn2.classList.remove('ha-in');
      setTimeout(() => {
        subZh.textContent = zh || '';
        subEn2.textContent = en || '';
        subZh.classList.add('ha-in');
        if (en) subEn2.classList.add('ha-in');
      }, ms(140));
    }

    function setStepCount(i: number, code: string) {
      const total = STEPS.length + 1;
      stepcount.textContent = '[ ' + String(i).padStart(2, '0') + ' / ' + String(total).padStart(2, '0') + ' ] ' + code;
    }

    function startHex() {
      function line() {
        let s = '';
        for (let i = 0; i < 26; i++) { s += '0123456789ABCDEF'.charAt(Math.floor(Math.random() * 16)); if (i % 2 === 1) s += ' '; }
        return s;
      }
      function paint() {
        const out: string[] = [];
        for (let i = 0; i < 12; i++) out.push(line());
        hex.innerHTML = out.join('<br>');
      }
      paint();
      hex.classList.add('ha-in');
      hexTimer = setInterval(paint, 110);
    }
    function stopHex() { if (hexTimer) { clearInterval(hexTimer); hexTimer = null; } hex.classList.remove('ha-in'); }

    function assembleLogo(): Promise<void> {
      logo.classList.add('ha-in');
      dots.hidden = false;
      const path = logo.querySelector('path') as SVGPathElement | null;
      if (path && typeof path.getTotalLength === 'function') {
        try {
          const len = path.getTotalLength();
          path.style.fill = 'none';
          path.style.stroke = 'currentColor';
          path.style.strokeWidth = '1.1';
          path.style.strokeDasharray = String(len);
          path.style.strokeDashoffset = String(len);
          path.animate(
            [{ strokeDashoffset: String(len) }, { strokeDashoffset: '0' }],
            { duration: ms(1400), easing: 'cubic-bezier(.55,.06,.24,1)', fill: 'forwards' }
          );
          setTimeout(() => {
            path.style.transition = `fill ${ms(420)}ms ease, stroke-width ${ms(420)}ms ease`;
            path.style.fill = '';
            path.style.strokeWidth = '0';
          }, ms(1450));
        } catch { /* noop */ }
      }
      return wait(300);
    }

    function showAction(step: StartupStep) {
      btnZh.textContent = step.btnZh || '';
      btnEn.textContent = step.btnEn || '';
      card.hidden = step.action !== 'confirm';
      if (step.action === 'confirm') {
        card.innerHTML = '';
        const rows: Array<[string, string, boolean]> = [
          ['身份名称', C.identity, true],
          ['身份编号', C.identityId, false],
          ['权限等级', C.accessLevel, false],
        ];
        for (const [label, value, isName] of rows) {
          const row = document.createElement('div');
          row.className = 'ha-card-row';
          row.innerHTML = `<span>${label}</span><b${isName ? ' class="ha-zhname"' : ''}>${value}</b>`;
          card.appendChild(row);
        }
      }
      hint.innerHTML = '按 <kbd>Enter</kbd> / <kbd>Space</kbd>，或点击按钮继续';
      actionEl.classList.add('ha-in');
      btn.classList.add('ha-pulse');
    }

    function hideAction() {
      actionEl.classList.remove('ha-in');
      btn.classList.remove('ha-pulse');
    }

    /* ── 时间线 ───────────────────────────────────────────────── */
    async function run() {
      try {
        /* 第一幕：黑幕 → 品牌标识 */
        await wait(820);
        blackInner.classList.add('ha-in');
        audio.rise();
        await wait(240);
        blackEn.classList.add('ha-tighten');
        await wait(880);
        sweepEl.classList.add('ha-go');
        await wait(760);

        /* 过场：过曝洗白 */
        blackInner.classList.add('ha-out');
        audio.sweep();
        wash.style.transition = `opacity ${ms(220)}ms linear`;
        wash.style.opacity = '1';
        await wait(260);
        plate.style.transition = `opacity ${ms(900)}ms ease`;
        plate.style.opacity = '1';
        watermark.style.transition = `opacity ${ms(1100)}ms ease`;
        watermark.style.opacity = '1';
        wash.style.transition = `opacity ${ms(720)}ms cubic-bezier(.2,.9,.2,1)`;
        wash.style.opacity = '0';
        black.style.transition = `opacity ${ms(720)}ms ease`;
        black.style.opacity = '0';
        await wait(760);

        /* 第二幕：品牌块 / 页脚 / 进度条 */
        brand.classList.add('ha-in');
        foot.classList.add('ha-in');
        stepcount.classList.add('ha-in');
        idline.classList.add('ha-in');
        frame.classList.add('ha-in');
        slats.classList.add('ha-in');
        meta.classList.add('ha-in');
        vignette.classList.add('ha-in');
        voice.classList.add('ha-in');
        setProgress(0.12);
        setStepCount(0, 'BOOT');
        setSlats(0);
        setSubtitle('系统自检中…', 'SYSTEM SELF-CHECK');
        if (C.allowSkip) skipBtn.classList.add('ha-in');
        await wait(700);
        black.style.display = 'none';
        sweep();

        /* 五个阶段 */
        for (let i = 0; i < STEPS.length; i++) {
          if (finished) break;
          const step = STEPS[i];
          const n = i + 1;
          setStepCount(n, step.badge);
          setSlats(n);
          setProgress(step.progress);
          setSubtitle(step.log, step.logEn);
          audio.step();

          const spoke = speakLine(step.say);

          status.classList.add('ha-zhline');
          status.classList.remove('ha-in');
          subEn.classList.remove('ha-in');
          void status.offsetWidth;
          typeIn(statusZh, step.zh, 46);
          typeIn(subEn, step.en, 13);
          caret.classList.toggle('ha-on', !!step.action && step.action !== 'auto');
          requestAnimationFrame(() => {
            if (finished) return;
            status.classList.add('ha-in');
            subEn.classList.add('ha-in');
          });
          rule.classList.add('ha-in');

          if (step.assembleLogo) await assembleLogo();
          if (step.reticle) {
            logo.classList.remove('ha-in');
            dots.hidden = true;
            reticle.classList.add('ha-in');
            sweep();
          }
          if (step.hex) startHex();

          function holdFor(spoken: number) {
            const target = Math.max(ms(step.hold), spoken + ms(240));
            return wait(Math.max(0, target - spoken));
          }

          if (step.action === 'grant' || step.action === 'confirm') {
            showAction(step);
            await wait(520);
            await waitAction();
            hideAction();
            audio.confirm();
            caret.classList.remove('ha-on');
            const spoken = await spoke;
            await wait(ms(320 + Math.max(0, spoken)));
          } else if (step.hex) {
            const spoken = await spoke;
            await holdFor(spoken);
            stopHex();
          } else {
            const spoken = await spoke;
            await holdFor(spoken);
          }
        }

        /* 终幕 */
        if (finished) return;
        setStepCount(STEPS.length + 1, 'WELCOME');
        setSlats(STEPS.length + 1);
        setProgress(1);
        setSubtitle('身份验证完成，会话已建立', 'IDENTITY VERIFIED · SESSION ESTABLISHED');
        audio.chime();

        status.classList.remove('ha-in');
        subEn.classList.remove('ha-in');
        rule.classList.remove('ha-in');
        reticle.classList.remove('ha-in');
        stopHex();
        center.classList.add('ha-off');
        dots.hidden = true;

        await wait(360);
        welcome.classList.add('ha-in');
        idline.classList.remove('ha-in');
        await wait(420);

        /* 色散故障 */
        const targets = [w1, w2, w4];
        targets.forEach(t => { t.classList.add('ha-glitch'); t.setAttribute('data-text', t.textContent || ''); });
        w2.classList.add('ha-glitch-box');
        void welcome.offsetWidth;
        targets.forEach(t => t.classList.add('ha-on'));
        await wait(640);

        /* 光晕 */
        root.classList.add('ha-peak');
        bloom.classList.add('ha-go');
        streak.classList.add('ha-go');
        await wait(430);

        flash.style.transition = `opacity ${ms(70)}ms linear`;
        flash.style.opacity = '0.72';
        await wait(90);
        flash.style.transition = `opacity ${ms(340)}ms cubic-bezier(0.4,0,0.2,1)`;
        flash.style.opacity = '0';
        await wait(320);

        /* 揭幕 */
        finish();
      } catch (err) {
        console.warn('[hermeneut-startup] animation error:', err);
        finish();
      }
    }

    /* ── 跳过 / ESC ───────────────────────────────────────────── */
    function requestSkip() {
      if (skipped || finished) return;
      skipped = true;
      releaseAll();
      stopVoice();
      stopHex();
      finish();
    }

    if (C.allowSkip) {
      skipBtn.hidden = false;
      skipBtn.addEventListener('click', (e) => { e.stopPropagation(); requestSkip(); });
    } else {
      skipBtn.hidden = true;
    }

    function onEsc(e: KeyboardEvent) { if (e.key === 'Escape') requestSkip(); }
    document.addEventListener('keydown', onEsc);

    /* ── 声卡解锁 ─────────────────────────────────────────────── */
    let unlocked = false;
    function unlock() {
      if (unlocked) return;
      unlocked = true;
      ac();
      try { if (speechSupported) window.speechSynthesis.resume(); } catch { /* noop */ }
      if (speechSupported && !saidOnce) {
        try {
          const w = new SpeechSynthesisUtterance(' ');
          w.volume = 0;
          if (pickedVoice) { w.voice = pickedVoice; w.lang = pickedVoice.lang; }
          window.speechSynthesis.speak(w);
        } catch { /* noop */ }
      }
      document.removeEventListener('pointerdown', unlock, true);
      document.removeEventListener('keydown', unlock, true);
    }
    document.addEventListener('pointerdown', unlock, true);
    document.addEventListener('keydown', unlock, true);

    /* ── 启动 ─────────────────────────────────────────────────── */
    setProgress(0.05);
    run();

    /* 9 秒兜底 */
    const safetyTimer = setTimeout(() => {
      if (!finished && !skipped) {
        console.warn('[hermeneut-startup] safety timeout');
        releaseAll();
        stopVoice();
        finish();
      }
    }, 9000);

    return () => {
      releaseAll();
      stopVoice();
      stopHex();
      if (clockTimer) clearInterval(clockTimer);
      clearTimeout(safetyTimer);
      document.removeEventListener('keydown', onEsc);
      document.removeEventListener('pointerdown', unlock, true);
      document.removeEventListener('keydown', unlock, true);
    };
  }, [finish, brandingOnly]);

  return <div ref={rootRef} className="ha-startup-root ha-boot" />;
}
