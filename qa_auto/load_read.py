#!/usr/bin/env python3
"""Read-only load test — keep-alive, focuses p95 on cheap endpoints.

Usage:
  QA_LOAD_TOKEN=... python3 qa_auto/load_read.py --workers 20 --seconds 10
  # local baseline on VPS:
  QA_HOST=127.0.0.1 QA_LOAD_TOKEN=... python3 qa_auto/load_read.py --workers 20
"""
from __future__ import annotations

import argparse
import http.client
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

HOST = os.environ.get("QA_HOST", "92.246.128.94")
PORT = int(os.environ.get("QA_LOAD_PORT", "8000"))
PW = os.environ.get("QA_KASKAD_PW", "kaskad2026")
COOKIE = os.environ.get("QA_LOAD_COOKIE", "crm_token_kaskad")

# cheap paths for primary p95; HTML mixed separately
CHEAP_PATHS = ["/health", "/api/bot/status"]
HTML_PATHS = ["/dashboard", "/bot"]


class NoRedir(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def get_token() -> str:
    env_tok = os.environ.get("QA_LOAD_TOKEN", "").strip()
    if env_tok:
        return env_tok
    last_err = ""
    for attempt in range(4):
        data = urllib.parse.urlencode({"password": PW}).encode()
        req = urllib.request.Request(f"http://{HOST}:{PORT}/login", data=data, method="POST")
        op = urllib.request.build_opener(NoRedir)
        try:
            with op.open(req, timeout=15) as resp:
                sc = dict(resp.headers).get("Set-Cookie", "")
                code = resp.status
        except urllib.error.HTTPError as e:
            sc = dict(e.headers).get("Set-Cookie", "")
            code = e.code
        m = re.search(re.escape(COOKIE) + r"=([^;]+)", sc)
        if m:
            return m.group(1)
        last_err = f"HTTP {code} Set-Cookie={sc[:160]!r}"
        time.sleep(16)
    raise SystemExit(f"login failed after retries: {last_err}")


def one_get_keepalive(path: str, cookie: str | None) -> tuple[str, int, float]:
    """GET with HTTP/1.1 keep-alive on a short-lived connection pool per call.
    Using http.client avoids urllib redirect/opener overhead."""
    headers = {"Host": HOST, "Connection": "keep-alive"}
    if cookie and path not in ("/health", "/login"):
        headers["Cookie"] = cookie
    t0 = time.perf_counter()
    code = 0
    try:
        conn = http.client.HTTPConnection(HOST, PORT, timeout=8)
        conn.request("GET", path, headers=headers)
        resp = conn.getresponse()
        code = resp.status
        resp.read(128)
        conn.close()
    except Exception:
        code = 0
    dt = (time.perf_counter() - t0) * 1000
    return path, code, dt


def percentile(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    k = (len(xs) - 1) * p / 100
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    if f == c:
        return xs[f]
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def run_phase(name: str, paths: list[str], workers: int, seconds: float, cookie: str):
    lat: list[float] = []
    codes: dict[int, int] = {}
    errors = 0
    total = 0
    deadline = time.perf_counter() + seconds

    def worker(i: int) -> list[tuple[str, int, float]]:
        out = []
        n = 0
        while time.perf_counter() < deadline:
            path = paths[(i + n) % len(paths)]
            out.append(one_get_keepalive(path, cookie))
            n += 1
        return out

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(worker, i) for i in range(workers)]
        for fut in futs:
            for path, code, dt in fut.result():
                total += 1
                lat.append(dt)
                codes[code] = codes.get(code, 0) + 1
                if code not in (200, 302, 401):
                    errors += 1
    elapsed = time.perf_counter() - t0
    err_rate = (errors / total * 100) if total else 0.0
    return {
        "name": name,
        "total": total,
        "elapsed": elapsed,
        "thr": (total / elapsed) if elapsed else 0,
        "err_rate": err_rate,
        "p50": percentile(lat, 50),
        "p95": percentile(lat, 95),
        "codes": codes,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=20)
    parser.add_argument("--seconds", type=float, default=10)
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()

    cookie_val = get_token()
    cookie_full = f"{COOKIE}={cookie_val}"
    print(f"host={HOST}:{args.port} workers={args.workers}s{args.seconds}")

    cheap = run_phase("cheap", CHEAP_PATHS, args.workers, args.seconds, cookie_full)
    html = run_phase("html", HTML_PATHS, max(5, args.workers // 2), max(5, args.seconds / 2), cookie_full)

    # sequential baseline (pure RTT + one request)
    seq_lat = []
    for _ in range(15):
        _, code, dt = one_get_keepalive("/health", None)
        if code == 200:
            seq_lat.append(dt)
    seq_p95 = percentile(seq_lat, 95)

    # success criteria: p95 < 1000ms primary (cheap), errors < 1%
    p95_ok = cheap["p95"] < 1000
    err_ok = cheap["err_rate"] < 1.0
    ok = p95_ok and err_ok

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report = Path(__file__).parent / f"report_load_{ts}.md"
    with report.open("w") as f:
        f.write("# Load report (keep-alive)\n\n")
        f.write(f"**UTC:** {ts}  \n**Host:** {HOST}:{args.port}  \n")
        f.write(f"**Result:** {'PASS' if ok else 'FAIL'} (cheap p95 {cheap['p95']:.0f}ms, need &lt;1000ms)\n\n")
        f.write("| Phase | req/s | p50 | p95 | err% | codes |\n|---|---|---|---|---|---|\n")
        for ph in (cheap, html):
            f.write(
                f"| {ph['name']} | {ph['thr']:.1f} | {ph['p50']:.1f} | {ph['p95']:.1f} | {ph['err_rate']:.2f} | {ph['codes']} |\n"
            )
        f.write(f"\nSequential /health p95: **{seq_p95:.1f} ms** (RTT baseline)\n")

    print(
        f"cheap p50={cheap['p50']:.1f} p95={cheap['p95']:.1f} thr={cheap['thr']:.1f}/s err={cheap['err_rate']:.2f}%"
    )
    print(f"html  p50={html['p50']:.1f} p95={html['p95']:.1f} thr={html['thr']:.1f}/s")
    print(f"seq /health p95={seq_p95:.1f}ms")
    print(f"RESULT {'PASS' if ok else 'FAIL'}")
    print("REPORT", report)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
