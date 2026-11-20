/* Shared accessibility enhancements (see a11y.css). Progressive: the pages work without it, it adds semantics,
 * keyboard operation, focus management and a text-size control. It also retrofits dynamically added content. */
(function () {
  'use strict';
  var STR = {
    en: { skip: 'Skip to main content', size: 'Text size', sizeNames: ['Normal text', 'Large text', 'Extra large text'], chat: 'Type your question', demoUser: 'Demo user', contact: "Relative's contact (phone or email)", close: 'Close' },
    ar: { skip: 'تخطَّ إلى المحتوى الرئيسي', size: 'حجم الخط', sizeNames: ['خط عادي', 'خط كبير', 'خط كبير جداً'], chat: 'اكتب سؤالك', demoUser: 'مستخدم تجريبي', contact: 'وسيلة تواصل القريب (هاتف أو بريد)', close: 'إغلاق' }
  };
  var lang = function () { return (document.documentElement.lang || 'en').slice(0, 2) === 'ar' ? 'ar' : 'en'; };
  var t = function (k) { return STR[lang()][k]; };
  var reduceMotion = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  var uid = 0;
  var nextId = function (p) { uid += 1; return p + '-' + uid; };

  /* Respect reduced motion for scripted smooth scrolling. */
  if (reduceMotion) {
    var orig = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = function (arg) {
      if (arg && typeof arg === 'object') { arg = Object.assign({}, arg, { behavior: 'auto' }); }
      return orig.call(this, arg);
    };
  }

  /* ---------- skip link + main landmark ---------- */
  function skipLink() {
    var main = document.querySelector('.container, main, .dashboard-content') || document.body;
    if (!main.id) main.id = 'main-content';
    main.setAttribute('tabindex', '-1');
    if (!main.getAttribute('role') && main.tagName !== 'MAIN') main.setAttribute('role', 'main');
    var a = document.querySelector('.skip-link');
    if (!a) {
      a = document.createElement('a');
      a.className = 'skip-link';
      document.body.insertBefore(a, document.body.firstChild);
    }
    a.href = '#' + main.id;
    a.textContent = t('skip');
    a.onclick = function (e) { e.preventDefault(); main.focus(); main.scrollIntoView(); };
  }

  /* ---------- headings (landmarks for screen-reader navigation) ---------- */
  function headings(root) {
    root.querySelectorAll('.brand-title, .packet-title').forEach(function (el) {
      if (!el.getAttribute('role')) { el.setAttribute('role', 'heading'); el.setAttribute('aria-level', '1'); }
    });
    root.querySelectorAll('.card-title, .section-title').forEach(function (el) {
      if (!el.getAttribute('role')) { el.setAttribute('role', 'heading'); el.setAttribute('aria-level', '2'); }
    });
    // table header cells need a scope for screen readers
    document.querySelectorAll('th:not([scope])').forEach(function (th) { th.setAttribute('scope', th.closest('thead') ? 'col' : 'row'); });
    // keep heading levels from skipping (h1 -> h3): adjust the exposed level, not the visual style
    var prevLevel = 0;
    document.querySelectorAll('h1,h2,h3,h4,h5,h6,[role="heading"]').forEach(function (h) {
      var lvl = parseInt(h.getAttribute('aria-level') || (h.tagName[0] === 'H' ? h.tagName[1] : '2'), 10);
      if (prevLevel && lvl > prevLevel + 1) { lvl = prevLevel + 1; h.setAttribute('aria-level', String(lvl)); }
      prevLevel = lvl;
    });
    root.querySelectorAll('.option-card h4').forEach(function (h) { h.setAttribute('role', 'heading'); h.setAttribute('aria-level', '3'); });
    if (!document.querySelector('h1, [role="heading"][aria-level="1"]')) {
      var h2 = document.querySelector('h2');
      if (h2) { h2.setAttribute('role', 'heading'); h2.setAttribute('aria-level', '1'); }
    }
  }

  /* ---------- clickable non-interactive elements become keyboard operable ---------- */
  function operable(root) {
    root.querySelectorAll('[onclick], .queue-card').forEach(function (el) {
      var native = /^(A|BUTTON|INPUT|SELECT|SUMMARY|LABEL|TEXTAREA)$/.test(el.tagName);
      if (native || el.dataset.a11yOp) return;
      el.dataset.a11yOp = '1';
      if (!el.getAttribute('role')) el.setAttribute('role', 'button');
      if (!el.hasAttribute('tabindex')) el.setAttribute('tabindex', '0');
      if (el.classList.contains('queue-card')) {
        var cur = function () { if (el.classList.contains('active')) el.setAttribute('aria-current', 'true'); else el.removeAttribute('aria-current'); };
        cur();
        new MutationObserver(cur).observe(el, { attributes: true, attributeFilter: ['class'] });
      }
      el.addEventListener('keydown', function (e) {
        if ((e.key === 'Enter' || e.key === ' ') && e.target === el) { e.preventDefault(); el.click(); }
      });
    });
  }

  /* ---------- accordion (layered explanation) ---------- */
  function accordions(root) {
    root.querySelectorAll('.layer-item').forEach(function (item) {
      var header = item.querySelector('.layer-header');
      var content = item.querySelector('.layer-content');
      if (!header || !content || header.dataset.a11yAcc) return;
      header.dataset.a11yAcc = '1';
      if (!content.id) content.id = nextId('layer-content');
      header.setAttribute('role', 'button');
      header.setAttribute('tabindex', '0');
      header.setAttribute('aria-controls', content.id);
      var sync = function () { header.setAttribute('aria-expanded', item.classList.contains('open') ? 'true' : 'false'); };
      sync();
      new MutationObserver(sync).observe(item, { attributes: true, attributeFilter: ['class'] });
      header.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); item.click(); }
      });
      var arrow = header.querySelector('span:last-child');
      if (arrow) arrow.setAttribute('aria-hidden', 'true');
      item.removeAttribute('role'); item.removeAttribute('tabindex'); // the header, not the wrapper, is the control
      item.dataset.a11yOp = '1';
    });
  }

  /* ---------- modals: dialog semantics, focus trap, Escape, focus return ---------- */
  var FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type=hidden]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
  function modals() {
    document.querySelectorAll('.modal-overlay').forEach(function (overlay) {
      if (overlay.dataset.a11yModal) return;
      overlay.dataset.a11yModal = '1';
      var dialog = overlay.querySelector('.modal') || overlay;
      dialog.setAttribute('role', 'dialog');
      dialog.setAttribute('aria-modal', 'true');
      var heading = dialog.querySelector('h1, h2, h3, h4, [role="heading"]');
      if (heading) { if (!heading.id) heading.id = nextId('dlg-title'); dialog.setAttribute('aria-labelledby', heading.id); }
      var opener = null;
      var onKey = function (e) {
        if (e.key === 'Escape') { e.preventDefault(); close(); return; }
        if (e.key !== 'Tab') return;
        var items = Array.prototype.filter.call(dialog.querySelectorAll(FOCUSABLE), function (n) { return n.offsetParent !== null; });
        if (!items.length) { e.preventDefault(); return; }
        var first = items[0], last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      };
      function close() {
        var btn = Array.prototype.find.call(dialog.querySelectorAll('button, [role="button"]'), function (b) { return /close|skip|cancel/i.test(b.getAttribute('onclick') || ''); });
        if (btn) btn.click(); else overlay.classList.remove('open');
      }
      var wasOpen = false;
      var sync = function () {
        var isOpen = overlay.classList.contains('open');
        if (isOpen && !wasOpen) {
          opener = document.activeElement && document.activeElement !== document.body ? document.activeElement : opener;
          dialog.setAttribute('aria-hidden', 'false');
          document.addEventListener('keydown', onKey, true);
          var items = dialog.querySelectorAll(FOCUSABLE);
          var target = heading || items[0] || dialog;
          if (!target.hasAttribute('tabindex')) target.setAttribute('tabindex', '-1');
          setTimeout(function () { target.focus(); }, 0);
        } else if (!isOpen && wasOpen) {
          document.removeEventListener('keydown', onKey, true);
          if (opener && document.contains(opener)) { try { opener.focus(); } catch (e) { /* ignore */ } }
          opener = null;
        }
        wasOpen = isOpen;
      };
      new MutationObserver(sync).observe(overlay, { attributes: true, attributeFilter: ['class'] });
      sync(); // modal that is already open when the page loads
    });
  }

  /* ---------- live regions for status messages ---------- */
  function liveRegions() {
    var polite = ['#chat-response-box', '#ck-status', '#val-status', '#fam-status', '#book-status', '#audio-status', '#couple-status-badge', '#access-history-status'];
    polite.forEach(function (sel) {
      var el = document.querySelector(sel);
      if (el && !el.getAttribute('aria-live')) { el.setAttribute('role', 'status'); el.setAttribute('aria-live', 'polite'); }
    });
    var alert = document.querySelector('#couple-hidden-block');
    if (alert && !alert.getAttribute('role')) alert.setAttribute('role', 'status');
  }

  /* ---------- names for controls that have none ---------- */
  function names() {
    var set = function (sel, key) { var el = document.querySelector(sel); if (el && !el.getAttribute('aria-label') && !(el.labels && el.labels.length)) el.setAttribute('aria-label', t(key)); };
    set('#chat-input', 'chat'); set('#demo-user', 'demoUser'); set('#fam-contact', 'contact');
    var play = document.getElementById('btn-play-audio');
    if (play && !play.dataset.a11yNamed) {
      play.dataset.a11yNamed = '1';
      var sync = function () { play.setAttribute('aria-label', (lang() === 'ar' ? 'تشغيل أو إيقاف الشرح الصوتي' : 'Play or pause the audio explanation')); };
      sync();
    }
    document.querySelectorAll('button[onclick*="closeBookingModal"], button[onclick*="closeAccessHistoryModal"], button[onclick*="closePlatformGuideModal"]').forEach(function (b) {
      if (!b.textContent.trim().replace(/[✕×x]/gi, '') && !b.getAttribute('aria-label')) b.setAttribute('aria-label', t('close'));
      else if (/^[✕×]$/.test(b.textContent.trim())) b.setAttribute('aria-label', t('close'));
    });
    document.querySelectorAll('label:not([for])').forEach(function (l) {
      var next = l.nextElementSibling;
      if (next && /^(SELECT|INPUT|TEXTAREA)$/.test(next.tagName) && next.id) l.setAttribute('for', next.id);
    });
  }

  /* ---------- toggle-button state ---------- */
  function pressed() {
    document.querySelectorAll('.format-btn, #btn-lang-ar, #btn-lang-en').forEach(function (b) {
      if (b.dataset.a11yPressed) return;
      b.dataset.a11yPressed = '1';
      var sync = function () { b.setAttribute('aria-pressed', b.classList.contains('active') ? 'true' : 'false'); };
      sync();
      new MutationObserver(sync).observe(b, { attributes: true, attributeFilter: ['class'] });
    });
    var play = document.getElementById('btn-play-audio');
    if (play && !play.dataset.a11yPressed) {
      play.dataset.a11yPressed = '1';
      var s = function () { play.setAttribute('aria-pressed', /⏸/.test(play.textContent) ? 'true' : 'false'); };
      s();
      new MutationObserver(s).observe(play, { childList: true, characterData: true, subtree: true });
    }
  }

  /* ---------- icon arrays: one text alternative instead of many unnamed dots ---------- */
  function iconArrays(root) {
    var seen = new Set();
    root.querySelectorAll('.icon-dot').forEach(function (dot) {
      var group = dot.parentElement;
      if (!group || seen.has(group) || group.dataset.a11yImg) return;
      seen.add(group);
      group.dataset.a11yImg = '1';
      var titles = [];
      group.querySelectorAll('.icon-dot').forEach(function (d) {
        var ti = d.getAttribute('title'); if (ti && titles.indexOf(ti) === -1) titles.push(ti);
        d.setAttribute('aria-hidden', 'true');
      });
      var heading = group.previousElementSibling;
      var prefix = heading && heading.textContent ? heading.textContent.trim() + ': ' : '';
      group.setAttribute('role', 'img');
      group.setAttribute('aria-label', prefix + titles.join(', '));
    });
  }

  /* ---------- text size control ---------- */
  function textSize() {
    var host = document.querySelector('.top-controls, .nav-links, .header-actions, header, .platform-nav') || document.body;
    if (document.getElementById('a11y-text-size')) return;
    var btn = document.createElement('button');
    btn.id = 'a11y-text-size'; btn.type = 'button'; btn.className = 'a11y-text-btn';
    var level = 0;
    try { level = parseInt(localStorage.getItem('a11yText') || '0', 10) || 0; } catch (e) { level = 0; }
    var apply = function () {
      document.documentElement.classList.remove('a11y-text-lg', 'a11y-text-xl');
      if (level === 1) document.documentElement.classList.add('a11y-text-lg');
      if (level === 2) document.documentElement.classList.add('a11y-text-xl');
      btn.textContent = ['A', 'A+', 'A++'][level];
      btn.setAttribute('aria-pressed', level > 0 ? 'true' : 'false');
      btn.setAttribute('aria-label', t('size') + ': ' + t('sizeNames')[level]);
    };
    btn.addEventListener('click', function () {
      level = (level + 1) % 3;
      try { localStorage.setItem('a11yText', String(level)); } catch (e) { /* storage may be blocked */ }
      apply();
    });
    apply();
    host.appendChild(btn);
    btn.__apply = apply;
  }

  function run(root) {
    root = root || document;
    headings(root); operable(root); accordions(root); iconArrays(root);
  }
  function all() {
    skipLink(); modals(); liveRegions(); names(); pressed(); textSize(); run(document);
  }

  function init() {
    all();
    // dynamic content (options, queue, quiz...) and language switches
    var timer = null;
    new MutationObserver(function () {
      clearTimeout(timer);
      timer = setTimeout(function () { run(document); names(); pressed(); liveRegions(); }, 60);
    }).observe(document.body, { childList: true, subtree: true });
    new MutationObserver(function () {
      skipLink(); names();
      var b = document.getElementById('a11y-text-size'); if (b && b.__apply) b.__apply();
    }).observe(document.documentElement, { attributes: true, attributeFilter: ['lang', 'dir'] });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
