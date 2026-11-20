# Accessibility pass (patient app, counsellor portal, dashboard)

Target: WCAG 2.2 level AA as a working goal. **No conformance claim is made**: axe-core, Lighthouse and a screen-reader
test have not been run (see "Not verified").

## What changed

Shared layer, loaded by all three pages: `app/assets/a11y.css` and `app/assets/a11y.js` (served at `/assets/`).

| Area | Change |
|---|---|
| Contrast | Brand tokens darkened (`--primary` #0f766e, `--secondary` #0369a1, `--danger` #b91c1c, `--text-muted` #475569, `--success` #047857). Inline colours that failed 4.5:1 were replaced. Icon-array dots use darker fills with white numbers. A unit test checks every colour pair used |
| Keyboard | Visible 3 px focus ring; skip-to-content link; layered-explanation headers and portal queue cards are real buttons (`role`, `tabindex`, Enter and Space, `aria-expanded` / `aria-current`); any other clickable `div` is retrofitted automatically |
| Dialogs | All modals get `role="dialog"`, `aria-modal`, `aria-labelledby`; focus moves in on open, Tab is trapped, Escape closes, focus returns to the opener |
| Structure | One `h1` per page, card titles exposed as level-2 headings, skipped heading levels corrected, `<th scope>`, main landmark |
| Names and labels | Chat box, demo-user switcher, relative-contact field, play button, close buttons and booking/check-in selects now have accessible names; quiz questions are `radiogroup`s |
| Dynamic content | Chat reply, status messages, consent badge and audio status are `aria-live="polite"` regions |
| Non-text content | Each icon array is one `role="img"` with a text description (for example "1 in 4 affected, 1 in 2 carrier, 1 in 4 neither"); meaning is never colour-only (numbers and legend text are present); toggle buttons expose `aria-pressed` |
| Text size and motion | A/A+/A++ text-size button (remembered, 100% / 112.5% / 125%); `prefers-reduced-motion` honoured, including scripted smooth scrolling; forced-colours rules |
| Audio | The read-aloud button no longer pretends to play: if the device has no voice for the language (common for Arabic) or playback fails, it says so and points to the written text |

Also fixed while testing: concurrent first-load requests made 401 errors and duplicate logins (`ensureLogin` now shares one promise).

## How it was checked

- `eval/a11y_audit.js` (first-party script, **not axe**): accessible names, form labels, clickable non-interactive
  elements, WCAG AA text contrast, duplicate IDs, heading order, `lang`, positive tabindex, touch targets, ARIA references.
  Baseline: 20 findings on the patient app, 50 on the portal, 4 on the dashboard. After the pass: 0 on all three.
  Run it by pasting the file into the browser console on each page.
- Real key presses in the built-in browser: Tab wraps inside an open dialog, Escape closes it and returns focus, Enter on an
  accordion header expands it, Enter on a focused queue card opens the case.
- `backend/tests/test_accessibility.py`: colour pairs meet AA, pages load the shared layer, zoom is not disabled, no positive
  `tabindex`, assets are served, dialog logic is present.
- Mobile emulation at 375 px with 100%, 112.5% and 125% text: no horizontal overflow detected.

## Not verified (do these before claiming anything)

1. **axe-core / Lighthouse**: loading axe from a CDN was blocked in this environment, so it was not run. Run it, or the
   browser extension, on `/app`, `/portal` and `/dashboard` in both languages.
2. **Screen readers**: not tested with NVDA, JAWS, VoiceOver or TalkBack, in English or Arabic. Reading order in RTL,
   live-region announcements and the `role="img"` descriptions need a real test.
3. **Arabic quality of accessible names**: the Arabic labels added here were written by the development team and are not reviewed.
4. **Audio**: there are no pre-recorded Arabic recordings. Read-aloud depends on a voice installed on the device.
   Recording the core explanations with a native speaker is still open.
5. **Voice input**, captions and sign-language support: not built.
6. **Cognitive accessibility** beyond reading-level settings (plain-language review with low-literacy users) is not done.
7. The audit covers visible content in its default state; hidden dialogs and every state of every screen were not each audited.

## Keeping it working

- Add new interactive widgets as real `<button>` / `<a>` elements; the retrofit is a safety net, not a design.
- Do not use colour as the only signal; keep text or numbers next to coloured badges.
- Re-run `eval/a11y_audit.js` and `pytest backend/tests/test_accessibility.py` after UI changes.
