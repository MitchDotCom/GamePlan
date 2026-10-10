"""Browser run against a RUNNING container (not an in-process server): claim, consent, answer, and check the rows the container stored.

  PYTHONPATH=src python3 qa/container_e2e.py --base http://localhost:8092 --claim-link http://localhost:8092/c/<token> --container recog [--hitter "Demo Hitter One"] [--engine chromium|webkit]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import engine_qa as Q  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402


def sql(container, q):
    out = subprocess.run(["docker", "exec", container, "python", "-c", f"import sqlite3,json;c=sqlite3.connect('/data/engine.db');print(json.dumps(c.execute({q!r}).fetchall()))"], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--claim-link", required=True)
    ap.add_argument("--container", required=True)
    ap.add_argument("--engine", default="chromium")
    ap.add_argument("--pack-prefix", default="Practice")
    a = ap.parse_args()
    Q.ARGS.update(engine=a.engine, only=[])
    with sync_playwright() as pw:
        B = Q.Browser(pw)
        ctx, p = B.page()
        Q.claim(p, a.claim_link)                                    # includes the consent click
        p.click("#tabs button[data-t=queue]")
        p.wait_for_selector("#packs .card", timeout=10000)
        titles = p.evaluate("[...document.querySelectorAll('#packs .card h2')].map(h => h.textContent)")
        print("playlist:", titles)
        Q.start_pack(p, titles[0])
        Q.answer_both(p)
        Q.finish_pitch(p)
        p.evaluate("window.__engine.flush(true)")
        p.wait_for_function("document.getElementById('pend').textContent.startsWith('0 ')", timeout=15000)
        who = p.inner_text("#whoTxt")
        n = sql(a.container, "SELECT COUNT(*), COUNT(DISTINCT player_id) FROM answers")
        cons = sql(a.container, "SELECT COUNT(*) FROM consents")
        errs = [e for e in B.errors]
        ctx.close()
        print("signed in as:", who, "| answers, distinct players:", n, "| consents:", cons, "| browser errors:", errs)
        ok = n[0][0] >= 2 and n[0][1] == 1 and cons[0][0] == 1 and not errs
        print("PASS" if ok else "FAIL")
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
