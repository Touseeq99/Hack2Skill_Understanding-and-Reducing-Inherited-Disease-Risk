"""Re-record the captioned, narrated demo video (Windows only: uses Chrome, Windows speech and ffmpeg).

One-time setup:  pip install playwright   and   python -m playwright install ffmpeg   (ffmpeg must also be on PATH)
Then start a server on a FRESH scratch database (so the recording does not dirty your demo data):

    set DATABASE_URL=sqlite:///C:/temp/video_demo.db
    python -m data.generate_seed && python -m data.seed_outcomes && python -m data.seed_cases
    python -m uvicorn backend.main:app --port 8790
    python tools/record_demo.py

Output (demo.mp4, about 3 minutes) is written next to this script. Edit STEPS to change captions and narration.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8790"
W, H = 1280, 720

STEPS = [
    ("intro", "Prototype on synthetic data  |  draft awaiting clinical sign-off",
     "This is a prototype of a private companion that helps couples in Abu Dhabi understand inherited disease risk. "
     "It uses synthetic data only, and its content is a draft awaiting clinical sign-off."),
    ("result", "1. A carrier result, explained in Arabic: not a diagnosis",
     "Fatima opens her result in Arabic. The app explains that she is a carrier, shows it with an icon array, and states clearly "
     "that this is a screening result, not a diagnosis. She can choose text, audio or illustrated formats."),
    ("quiz", "2. Layered explanation and a teach-back check",
     "The explanation comes in layers, including what the result does not mean. A short teach-back quiz checks understanding. "
     "If someone fails twice, a counsellor is offered automatically."),
    ("consent", "3. Mutual consent: revoke hides the result for both partners",
     "Fatima and Tariq each control what the other can see. The joint result appears only while both consents are active. "
     "When Fatima revokes, it disappears for both partners immediately. Granting again brings it back."),
    ("decision", "4. 'Should we still get married?' is never answered",
     "If she asks whether they should still get married, the assistant never answers. It gives a fixed, non-directive message, "
     "opens a priority case, and shows which rules fired."),
    ("faq", "5. Education answers come only from an approved library",
     "For education questions, the assistant returns text from an approved library, word for word. No generated text reaches the user."),
    ("distress", "6. Distress or coercion triggers crisis contacts and escalation",
     "Messages that suggest distress or coercion show crisis contacts straight away and escalate to a human."),
    ("options", "7. Neutral options; detailed ones unlock after counselling",
     "The options library shows seven neutral choices. Detailed options stay locked until counselling has happened. "
     "Her values answers stay private unless she chooses to share them."),
    ("family", "8. Anonymous family notice and a tamper-evident access history",
     "She can tell relatives with a general card, or send an anonymous notice that never reveals who sent it. "
     "Every access to her data is recorded in a tamper-evident log that she can read."),
    ("portal", "9. Counsellor portal: queue, findings, case packet",
     "Counsellors see a queue sorted by urgency and service level, with the full case: findings, couple outcome, the rules that fired, "
     "quiz score, values the patient chose to share, and a tracked referral path."),
    ("dashboard", "10. Outcomes dashboard computed from stored data",
     "The dashboard computes comprehension uplift, counselling uptake, revocations honoured and equity gaps from stored data. "
     "It shows how many people each figure rests on, and says no data yet where nothing was measured. "
     "Cancelled marriages are never a success metric."),
    ("end", "Limits: synthetic data | no clinical review yet | safety classifier has false alarms",
     "This is a prototype. It uses synthetic data, it has no clinical sign-off yet, and the safety classifier flags about one harmless "
     "message in four. Our submission document lists every limitation. Thank you."),
]

INIT_JS = """
(() => {
  const install = () => {
    if (document.getElementById('__cap')) return;
    const cap = document.createElement('div'); cap.id = '__cap';
    cap.style.cssText = 'position:fixed;left:0;right:0;bottom:0;z-index:2147483647;background:rgba(15,23,42,.92);color:#fff;font:600 21px/1.35 Segoe UI,Arial,sans-serif;padding:14px 28px;text-align:center;direction:ltr;pointer-events:none';
    cap.textContent = window.__capText || '';
    document.documentElement.appendChild(cap);
    const cur = document.createElement('div'); cur.id = '__cur';
    cur.style.cssText = 'position:fixed;z-index:2147483647;width:22px;height:22px;border-radius:50%;background:rgba(239,68,68,.75);border:2px solid #fff;pointer-events:none;transform:translate(-50%,-50%);left:-50px;top:-50px;transition:left .05s,top .05s';
    document.documentElement.appendChild(cur);
    addEventListener('mousemove', e => { cur.style.left = e.clientX + 'px'; cur.style.top = e.clientY + 'px'; }, true);
  };
  if (document.readyState === 'loading') addEventListener('DOMContentLoaded', install); else install();
  new MutationObserver(install).observe(document.documentElement, {childList: true});
})();
"""


def make_narration():
    out = HERE / "narr"
    out.mkdir(exist_ok=True)
    texts = {k: n for k, _, n in STEPS}
    (HERE / "narr_texts.json").write_text(json.dumps(texts), encoding="utf-8")
    ps = (
        "Add-Type -AssemblyName System.Speech; $t = Get-Content -Raw -Encoding UTF8 '%s' | ConvertFrom-Json; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.SelectVoice('Microsoft Zira Desktop'); $s.Rate = 0; "
        "foreach ($p in $t.PSObject.Properties) { $s.SetOutputToWaveFile('%s\\' + $p.Name + '.wav'); $s.Speak($p.Value); $s.SetOutputToNull() }"
        % (str(HERE / "narr_texts.json"), str(out))
    )
    subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], check=True)
    durs = {}
    for k, _, _ in STEPS:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out / f"{k}.wav")],
                           capture_output=True, text=True, check=True)
        durs[k] = float(r.stdout.strip())
    return durs


def smooth_click(page, selector, pause=0.5, timeout=4000):
    try:
        loc = page.locator(selector).first
        loc.scroll_into_view_if_needed(timeout=timeout)
        box = loc.bounding_box(timeout=timeout)
        if box:
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=18)
        time.sleep(0.25)
        loc.click(timeout=timeout)
        time.sleep(pause)
        return True
    except Exception as e:  # keep recording even if a selector is missing
        print("  (skipped click)", selector, str(e)[:80])
        return False


def scroll_to(page, selector, block="start", pause=0.6):
    try:
        page.evaluate("(s) => { const e = document.querySelector(s); if (e) e.scrollIntoView({behavior: 'smooth', block: '%s'}); }" % block, selector)
        time.sleep(pause)
    except Exception as e:
        print("  (skipped scroll)", selector, str(e)[:80])


def type_in(page, selector, text, delay=45):
    try:
        loc = page.locator(selector).first
        loc.scroll_into_view_if_needed(timeout=4000)
        box = loc.bounding_box()
        if box:
            page.mouse.move(box["x"] + 40, box["y"] + box["height"] / 2, steps=15)
        loc.click()
        loc.fill("")
        page.keyboard.type(text, delay=delay)
    except Exception as e:
        print("  (skipped type)", selector, str(e)[:80])


def run():
    durs = make_narration()
    print("narration seconds:", {k: round(v, 1) for k, v in durs.items()}, "total", round(sum(durs.values()), 1))
    starts = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport={"width": W, "height": H}, record_video_dir=str(HERE / "raw"),
                                  record_video_size={"width": W, "height": H}, locale="en-GB")
        ctx.add_init_script(INIT_JS)
        page = ctx.new_page()
        page.on("dialog", lambda d: d.accept())
        t0 = time.time()

        def caption(text):
            page.evaluate("(t) => { window.__capText = t; const c = document.getElementById('__cap'); if (c) c.textContent = t; }", text)

        def begin(key):
            cap = next(c for k, c, _ in STEPS if k == key)
            caption(cap)
            starts[key] = time.time() - t0
            return time.time()

        def finish(key, t_begin, extra=0.6):
            remaining = durs[key] + extra - (time.time() - t_begin)
            if remaining > 0:
                time.sleep(remaining)

        page.goto(BASE + "/app")
        page.wait_for_load_state("networkidle")
        time.sleep(1.2)

        # intro: leave the opening dialog visible
        tb = begin("intro"); finish("intro", tb)

        # 1. Arabic result
        tb = begin("result")
        smooth_click(page, "#t-btn-ready-skip", pause=1.0)
        scroll_to(page, "#t-result-header", pause=1.0)
        smooth_click(page, "#fmt-audio", pause=0.8)
        smooth_click(page, "#fmt-visual", pause=1.0)
        smooth_click(page, "#fmt-text", pause=0.6)
        scroll_to(page, "#layered-explanation", pause=0.8)
        smooth_click(page, ".layer-item:nth-child(2) .layer-header", pause=1.0)
        smooth_click(page, ".layer-item:nth-child(3) .layer-header", pause=1.0)
        finish("result", tb)

        # 2. English, layers and quiz
        tb = begin("quiz")
        smooth_click(page, "#btn-lang-en", pause=1.2)
        scroll_to(page, "#quiz-section", pause=1.0)
        page.wait_for_timeout(500)
        for sel in ("#lbl_q1_carrier_meaning_b", "#lbl_q2_risk_vs_diagnosis_a", "#lbl_q3_same_gene_probability_a", "#lbl_q4_residual_risk_b"):
            smooth_click(page, sel, pause=0.5)
        smooth_click(page, "#btn-submit-quiz", pause=1.2)
        finish("quiz", tb)

        # 3. consent
        tb = begin("consent")
        scroll_to(page, "#couple-status-badge", block="center", pause=1.2)
        smooth_click(page, "#btn-revoke-cpl", pause=1.8)
        smooth_click(page, "#btn-grant-cpl", pause=1.8)
        finish("consent", tb)

        # 4. decision question
        tb = begin("decision")
        scroll_to(page, "#chat-assistant-card", pause=1.0)
        type_in(page, "#chat-input", "Should we still get married?")
        smooth_click(page, "#btn-send-chat", pause=2.0)
        finish("decision", tb)

        # 5. FAQ
        tb = begin("faq")
        type_in(page, "#chat-input", "What does being a carrier mean?")
        smooth_click(page, "#btn-send-chat", pause=2.0)
        finish("faq", tb)

        # 6. distress
        tb = begin("distress")
        type_in(page, "#chat-input", "I feel hopeless and I don't want to go on")
        smooth_click(page, "#btn-send-chat", pause=2.0)
        finish("distress", tb)

        # 7. options and values
        tb = begin("options")
        scroll_to(page, "#options-library-card", pause=1.2)
        page.evaluate("window.scrollBy({top: 380, behavior: 'smooth'})"); time.sleep(1.2)
        smooth_click(page, "#val-share", pause=0.5)
        smooth_click(page, "#val-save", pause=1.0)
        finish("options", tb)

        # 8. family + access history
        tb = begin("family")
        scroll_to(page, "#family-card", pause=1.0)
        smooth_click(page, "#fam-btn-card", pause=1.2)
        smooth_click(page, "#fam-btn-notice", pause=0.8)
        type_in(page, "#fam-contact", "+971500000000")
        smooth_click(page, "#fam-send", pause=1.2)
        smooth_click(page, "#btn-view-audit", pause=2.0)
        page.keyboard.press("Escape"); time.sleep(0.6)
        finish("family", tb)

        # 9. portal
        tb = begin("portal")
        page.goto(BASE + "/portal"); page.wait_for_load_state("networkidle"); time.sleep(1.5)
        caption(next(c for k, c, _ in STEPS if k == "portal"))
        smooth_click(page, "#queue-list .queue-card:nth-child(2)", pause=1.2)
        page.evaluate("window.scrollBy({top: 420, behavior: 'smooth'})"); time.sleep(1.5)
        page.evaluate("window.scrollBy({top: 420, behavior: 'smooth'})"); time.sleep(1.5)
        finish("portal", tb)

        # 10. dashboard
        tb = begin("dashboard")
        page.goto(BASE + "/dashboard"); page.wait_for_load_state("networkidle"); time.sleep(2.0)
        caption(next(c for k, c, _ in STEPS if k == "dashboard"))
        page.evaluate("window.scrollBy({top: 450, behavior: 'smooth'})"); time.sleep(2.0)
        page.evaluate("window.scrollBy({top: 450, behavior: 'smooth'})"); time.sleep(2.0)
        finish("dashboard", tb)

        # end card
        tb = begin("end"); finish("end", tb, extra=1.2)

        ctx.close()
        browser.close()

    raws = sorted((HERE / "raw").glob("*.webm"), key=lambda x: x.stat().st_mtime)
    raw = raws[-1]
    (HERE / "starts.json").write_text(json.dumps(starts), encoding="utf-8")
    print("video:", raw, "starts:", {k: round(v, 1) for k, v in starts.items()})

    # build the audio track: each narration clip delayed to its step start
    inputs, filters = [], []
    for i, (k, _, _) in enumerate(STEPS):
        inputs += ["-i", str(HERE / "narr" / f"{k}.wav")]
        ms = int(starts[k] * 1000)
        filters.append(f"[{i}:a]adelay={ms}|{ms}[a{i}]")
    mix = "".join(f"[a{i}]" for i in range(len(STEPS))) + f"amix=inputs={len(STEPS)}:normalize=0[aout]"
    subprocess.run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filters) + ";" + mix, "-map", "[aout]", str(HERE / "narration.wav")],
                   check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-i", str(raw), "-i", str(HERE / "narration.wav"), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-crf", "23", "-preset", "medium", "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart",
                    str(HERE / "demo.mp4")], check=True, capture_output=True)
    print("wrote", HERE / "demo.mp4")


if __name__ == "__main__":
    run()
