/* First-party accessibility audit (NOT axe-core). Paste into the browser console on /app, /portal or /dashboard,
 * or run through the preview tooling. Returns a list of findings; an empty list means none of THESE checks fired.
 * Checks: accessible names, form-control labels, clickable non-interactive elements, text contrast (WCAG AA),
 * duplicate ids, heading order, <html lang>, positive tabindex, small touch targets, ARIA references.
 * It is a supplement to, not a replacement for, axe / Lighthouse / a screen-reader test.
 */
(function () {
  const out = [];
  const add = (rule, el, detail) => out.push({ rule, node: (el.tagName || '').toLowerCase() + (el.id ? '#' + el.id : '') + (el.className && typeof el.className === 'string' ? '.' + el.className.split(' ')[0] : ''), detail: detail || '' });
  const visible = (el) => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
  const text = (el) => (el.innerText || el.textContent || '').trim();

  function accName(el) {
    const lb = el.getAttribute('aria-labelledby');
    if (lb) { const t = lb.split(/\s+/).map(i => document.getElementById(i)).filter(Boolean).map(text).join(' ').trim(); if (t) return t; }
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label').trim();
    if (el.labels && el.labels.length) { const t = [...el.labels].map(text).join(' ').trim(); if (t) return t; }
    if (el.tagName === 'INPUT' && ['button', 'submit'].includes(el.type)) return el.value;
    if (el.getAttribute('title')) return el.getAttribute('title').trim();
    if (el.placeholder && ['INPUT', 'TEXTAREA'].includes(el.tagName)) return ''; // placeholder is not a label
    return text(el) || (el.querySelector('img[alt]') ? el.querySelector('img[alt]').alt : '');
  }

  if (!document.documentElement.lang) add('html-lang', document.documentElement);

  // names of interactive elements
  document.querySelectorAll('a[href],button,[role=button],[role=link],input:not([type=hidden]),select,textarea,summary,[tabindex]').forEach(el => {
    if (!visible(el)) return;
    if (!accName(el)) add('no-accessible-name', el);
    const tab = el.getAttribute('tabindex');
    if (tab && parseInt(tab, 10) > 0) add('positive-tabindex', el, tab);
  });

  // clickable things that are not keyboard operable
  document.querySelectorAll('[onclick]').forEach(el => {
    if (!visible(el)) return;
    const native = ['A', 'BUTTON', 'INPUT', 'SELECT', 'SUMMARY', 'LABEL', 'TEXTAREA'].includes(el.tagName);
    const role = el.getAttribute('role');
    const focusable = el.hasAttribute('tabindex');
    if (!native && !(role && focusable) && !el.querySelector('[role=button][tabindex],button,a[href]')) add('click-not-keyboard-operable', el);
  });

  // headings
  let prev = 0;
  document.querySelectorAll('h1,h2,h3,h4,h5,h6,[role=heading]').forEach(h => {
    if (!visible(h)) return;
    const l = parseInt(h.getAttribute('aria-level') || (h.tagName[0] === 'H' ? h.tagName[1] : '2'), 10);
    if (prev && l > prev + 1) add('heading-skip', h, `h${prev} -> h${l}`);
    prev = l;
  });
  if (!document.querySelector('h1, [role=heading][aria-level="1"]')) add('no-h1', document.body);

  // duplicate ids and broken ARIA references
  const seen = {};
  document.querySelectorAll('[id]').forEach(el => { if (seen[el.id]) add('duplicate-id', el); seen[el.id] = 1; });
  document.querySelectorAll('[aria-labelledby],[aria-describedby],[aria-controls]').forEach(el => {
    ['aria-labelledby', 'aria-describedby', 'aria-controls'].forEach(a => {
      (el.getAttribute(a) || '').split(/\s+/).filter(Boolean).forEach(id => { if (!document.getElementById(id)) add('aria-broken-reference', el, a + '=' + id); });
    });
  });

  // images
  document.querySelectorAll('img').forEach(i => { if (!i.hasAttribute('alt')) add('img-alt', i); });

  // touch target size (WCAG 2.2 AA: 24x24 CSS px)
  document.querySelectorAll('a[href],button,select,input:not([type=hidden]):not([type=radio]):not([type=checkbox])').forEach(el => {
    if (!visible(el)) return;
    const r = el.getBoundingClientRect();
    if (r.width < 24 || r.height < 24) add('small-target', el, Math.round(r.width) + 'x' + Math.round(r.height));
  });

  // contrast
  function rgba(c) { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(',').map(parseFloat); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; }
  function lum(c) { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); }
  function bgOf(el) {
    let layers = [];
    for (let n = el; n; n = n.parentElement) {
      const cs = getComputedStyle(n);
      if (cs.backgroundImage && cs.backgroundImage !== 'none') return null; // gradients: skip, cannot compute reliably
      const c = rgba(cs.backgroundColor);
      if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; }
    }
    let base = { r: 255, g: 255, b: 255 };
    for (let i = layers.length - 1; i >= 0; i--) { const c = layers[i]; base = { r: c.r * c.a + base.r * (1 - c.a), g: c.g * c.a + base.g * (1 - c.a), b: c.b * c.a + base.b * (1 - c.a) }; }
    return base;
  }
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const checked = new Set();
  while (walker.nextNode()) {
    const n = walker.currentNode;
    if (!n.nodeValue.trim()) continue;
    const el = n.parentElement;
    if (!el || checked.has(el) || !visible(el)) continue;
    checked.add(el);
    const cs = getComputedStyle(el);
    const fg = rgba(cs.color); const bg = bgOf(el);
    if (!fg || !bg) continue;
    const L1 = lum({ r: fg.r * fg.a + bg.r * (1 - fg.a), g: fg.g * fg.a + bg.g * (1 - fg.a), b: fg.b * fg.a + bg.b * (1 - fg.a) }), L2 = lum(bg);
    const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    const size = parseFloat(cs.fontSize), bold = parseInt(cs.fontWeight, 10) >= 700;
    const large = size >= 24 || (size >= 18.66 && bold);
    const need = large ? 3 : 4.5;
    if (ratio < need) add('low-contrast', el, ratio.toFixed(2) + ':1 (needs ' + need + ') "' + text(el).slice(0, 30) + '"');
  }
  const summary = {};
  out.forEach(f => { summary[f.rule] = (summary[f.rule] || 0) + 1; });
  return { total: out.length, summary, findings: out };
})();
