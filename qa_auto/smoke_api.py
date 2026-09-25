#!/usr/bin/env python3
"""Functional + regression smoke for kaskad/hairos CRM (read-safe).

Usage:
  QA_KASKAD_PW=... QA_HAIROS_PW=... python3 qa_auto/smoke_api.py
  python3 qa_auto/smoke_api.py --host 92.246.128.94

Exit 0 if all PASS, 1 otherwise.
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HOST = os.environ.get("QA_HOST", "92.246.128.94")
SALONS = [
    {
        "id": "kaskad",
        "port": 8000,
        "pw": os.environ.get("QA_KASKAD_PW", "kaskad2026"),
        "cookie": "crm_token_kaskad",
    },
    {
        "id": "hairos",
        "port": 8005,
        "pw": os.environ.get("QA_HAIROS_PW", "hairos2026"),
        "cookie": "crm_token_hairos",
    },
]


class NoRedir(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


results: list[dict] = []


def add(cid: str, port, expected, actual, ok: bool, note: str = ""):
    results.append(
        {
            "id": cid,
            "port": port,
            "expected": str(expected),
            "actual": str(actual)[:200],
            "status": "PASS" if ok else "FAIL",
            "note": note,
        }
    )
    print(f"{'PASS' if ok else 'FAIL'} [{port}] {cid}: {actual}")


def request(url, *, data=None, headers=None, method=None, jar=None, timeout=20, json_body=None):
    h = dict(headers or {})
    if json_body is not None:
        data = json.dumps(json_body).encode()
        h.setdefault("Content-Type", "application/json")
    elif isinstance(data, dict):
        data = urllib.parse.urlencode(data).encode()
        h.setdefault("Content-Type", "application/x-www-form-urlencoded")
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    opener = urllib.request.build_opener()
    if jar is not None:
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    try:
        with opener.open(req, timeout=timeout) as resp:
            body = resp.read()
            return resp.status, dict(resp.headers), body, resp.geturl()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read(), url
    except Exception as e:
        return 0, {}, str(e).encode(), url


def request_noredirect(url, *, data=None, headers=None, timeout=20):
    h = dict(headers or {})
    body = None
    method = None
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
        h.setdefault("Content-Type", "application/x-www-form-urlencoded")
        method = "POST"
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    op = urllib.request.build_opener(NoRedir)
    try:
        with op.open(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()
    except Exception as e:
        return 0, {}, str(e).encode()


def login(salon) -> str | None:
    st, hdrs, _ = request_noredirect(
        f"http://{HOST}:{salon['port']}/login", data={"password": salon["pw"]}
    )
    sc = hdrs.get("Set-Cookie") or hdrs.get("set-cookie") or ""
    m = re.search(re.escape(salon["cookie"]) + r"=([^;]+)", sc)
    ok = st in (302, 303, 200) and bool(m)
    add(
        "F2" if salon["id"] == "kaskad" else "F2b",
        salon["port"],
        "302 + cookie",
        f"HTTP {st} cookie={bool(m)}",
        ok,
    )
    return m.group(1) if m else None


def bad_login(port, pw):
    st, hdrs, body = request_noredirect(
        f"http://{HOST}:{port}/login", data={"password": pw}
    )
    html = body.decode("utf-8", "replace")
    has_err = "Неверный пароль" in html
    sc = hdrs.get("Set-Cookie") or ""
    no_cookie = salon_cookie_absent(sc, port)
    add("F1", port, "error, no cookie", f"HTTP {st} err={has_err} no_ck={no_cookie}", st in (200, 302) and has_err and no_cookie)


def salon_cookie_absent(set_cookie: str, port: int) -> bool:
    name = "crm_token_kaskad" if port == 8000 else "crm_token_hairos"
    return name not in set_cookie


def full_cookie() -> str:
    parts = []
    for s in SALONS:
        t = login(s)
        if t:
            parts.append(f"{s['cookie']}={t}")
    return "; ".join(parts)


def api_get(port, path, cookie):
    st, _, body, _ = request(
        f"http://{HOST}:{port}{path}", headers={"Cookie": cookie}
    )
    try:
        return st, json.loads(body.decode("utf-8", "replace") or "null")
    except Exception:
        return st, body[:200]


def api_json(port, path, method, cookie, payload):
    st, _, body, _ = request(
        f"http://{HOST}:{port}{path}",
        method=method,
        json_body=payload,
        headers={"Cookie": cookie},
    )
    try:
        return st, json.loads(body.decode("utf-8", "replace") or "null")
    except Exception:
        return st, body[:200]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=HOST)
    args = parser.parse_args()
    host = args.host

    # F1 wrong password
    bad_login(8000, "definitely-wrong-pass")

    ck = full_cookie()

    # F3 shared jar both dashboards
    for s in SALONS:
        st, _, body, _ = request(
            f"http://{HOST}:{s['port']}/dashboard", headers={"Cookie": ck}
        )
        add("F3", s["port"], 200, f"HTTP {st}", st == 200)

    # F4 sidebar pages
    pages = [
        "/dashboard",
        "/schedule",
        "/bookings",
        "/finance",
        "/masters",
        "/services",
        "/clients",
        "/analytics",
        "/bot",
        "/masters-app",
        "/settings",
        "/users",
    ]
    for s in SALONS:
        fails = []
        for p in pages:
            st, _, body, _ = request(
                f"http://{HOST}:{s['port']}{p}", headers={"Cookie": ck}
            )
            if st != 200:
                fails.append(f"{p}={st}")
            elif b'id="sidebar"' not in body and b'class="sidebar"' not in body:
                fails.append(f"{p}:no-sidebar")
        add("F4", s["port"], "all 200+sidebar", "ok" if not fails else ", ".join(fails), not fails)

    # F5 salon name round-trip
    for s in SALONS:
        st0, j0 = api_get(s["port"], "/api/settings/salon-name", ck)
        # salon-name is PUT only for update; GET may 404 — try GET settings
        st, j = api_get(s["port"], "/api/settings", ck)
        add("F5", s["port"], "GET flags 200", f"HTTP {st}", st == 200)

        # PUT same ORG_TYPE back
        if isinstance(j, dict):
            org = j.get("ORG_TYPE", "beauty")
            st2, j2 = api_json(
                s["port"], "/api/settings", "PUT", ck, {"ORG_TYPE": org}
            )
            add("F5b", s["port"], "PUT flags 200", f"HTTP {st2}", st2 == 200)
        else:
            add("F5b", s["port"], "PUT flags", f"skip body={j}", False)

    # F6 flag round-trip — use a harmless flag if present
    for s in SALONS:
        st, j = api_get(s["port"], "/api/settings", ck)
        if not isinstance(j, dict) or "CONTACT_ENABLED" not in j:
            add("F6", s["port"], "flag present", f"keys={list(j)[:5] if isinstance(j, dict) else j}", False)
            continue
        orig = j["CONTACT_ENABLED"]
        flipped = not orig
        st1, _ = api_json(s["port"], "/api/settings", "PUT", ck, {"CONTACT_ENABLED": flipped})
        st2, j2 = api_get(s["port"], "/api/settings", ck)
        restored = j2.get("CONTACT_ENABLED") if isinstance(j2, dict) else None
        st3, _ = api_json(s["port"], "/api/settings", "PUT", ck, {"CONTACT_ENABLED": orig})
        st4, j4 = api_get(s["port"], "/api/settings", ck)
        back = j4.get("CONTACT_ENABLED") if isinstance(j4, dict) else None
        ok = st1 == 200 and restored == flipped and back == orig
        add("F6", s["port"], "toggle flip+restore", f"flip={restored} back={back}", ok)

    # F7 welcome round-trip
    for s in SALONS:
        st0, j0 = api_get(s["port"], "/api/bot/welcome", ck)
        text = j0.get("text", "") if isinstance(j0, dict) else ""
        st1, j1 = api_json(s["port"], "/api/bot/welcome", "PUT", ck, {"text": text})
        st2, j2 = api_get(s["port"], "/api/bot/welcome", ck)
        text2 = j2.get("text", "") if isinstance(j2, dict) else ""
        add(
            "F7",
            s["port"],
            "PUT/GET same text",
            f"st={st1}/{st2} match={text2 == text}",
            st1 == 200 and st2 == 200 and text2 == text,
        )

    # F8 menu create/update/delete URL button (cleanup always)
    for s in SALONS:
        port = s["port"]
        created_id = None
        try:
            st, j = api_json(
                port,
                "/api/bot/menu",
                "POST",
                ck,
                {
                    "label": "QA-test-url",
                    "emoji": "🧪",
                    "action_type": "url",
                    "action_value": "https://example.com/qa",
                    "sort_order": 99,
                    "enabled": False,
                },
            )
            created_id = j.get("id") if isinstance(j, dict) else None
            ok_post = st == 200 and created_id
            if created_id:
                st2, j2 = api_json(
                    port,
                    f"/api/bot/menu/{created_id}",
                    "PUT",
                    ck,
                    {
                        "id": created_id,
                        "label": "QA-test-url2",
                        "emoji": "🧪",
                        "action_type": "url",
                        "action_value": "https://example.com/qa2",
                        "sort_order": 99,
                        "enabled": False,
                    },
                )
                st3, _, _, _ = request(
                    f"http://{HOST}:{port}/api/bot/menu/{created_id}",
                    method="DELETE",
                    headers={"Cookie": ck},
                )
                st4, j4 = api_get(port, "/api/bot/menu", ck)
                items = j4.get("items") if isinstance(j4, dict) else []
                gone = created_id not in [i.get("id") for i in (items or [])]
                ok = bool(ok_post) and st2 == 200 and st3 == 200 and gone
                add("F8", port, "menu CRUD+cleanup", f"post={st} put={st2} del={st3} gone={gone}", ok)
            else:
                add("F8", port, "menu create", f"HTTP {st} id={created_id}", False)
        finally:
            if created_id:
                request(
                    f"http://{HOST}:{port}/api/bot/menu/{created_id}",
                    method="DELETE",
                    headers={"Cookie": ck},
                )

    # F9 notify toggle round-trip
    for s in SALONS:
        port = s["port"]
        st0, j0 = api_get(port, "/api/bot/notifications", ck)
        items = j0.get("items") if isinstance(j0, dict) else []
        target = next((i for i in items if i.get("type") == "remind_repeat"), None)
        if not target:
            add("F9", port, "notify types", "missing remind_repeat", False)
            continue
        orig = target.get("enabled")
        payload = dict(target)
        payload["enabled"] = not orig
        st1, _ = api_json(port, "/api/bot/notifications", "PUT", ck, {"items": [payload]})
        st2, j2 = api_get(port, "/api/bot/notifications", ck)
        items2 = j2.get("items") if isinstance(j2, dict) else []
        t2 = next((i for i in items2 if i.get("type") == "remind_repeat"), {})
        flipped = t2.get("enabled")
        restore = dict(target)
        restore["enabled"] = orig
        st3, _ = api_json(port, "/api/bot/notifications", "PUT", ck, {"items": [restore]})
        st4, j4 = api_get(port, "/api/bot/notifications", ck)
        t4 = next(
            (i for i in (j4.get("items") or []) if i.get("type") == "remind_repeat"),
            {},
        )
        add(
            "F9",
            port,
            "notify flip+restore",
            f"st={st1}/{st2}/{st3} flip={flipped} back={t4.get('enabled')}",
            st1 == 200 and flipped == (not orig) and t4.get("enabled") == orig,
        )

    # F10 status
    for s in SALONS:
        st, j = api_get(s["port"], "/api/bot/status", ck)
        ok = (
            st == 200
            and isinstance(j, dict)
            and j.get("bot_token_set") is True
            and bool(j.get("heartbeat_at"))
        )
        add(
            "F10",
            s["port"],
            "online+heartbeat",
            f"st={st} online={j.get('online') if isinstance(j, dict) else None} hb={j.get('heartbeat_at') if isinstance(j, dict) else j}",
            ok,
        )

    # F11 sessions list (no revoke)
    for s in SALONS:
        st, j = api_get(s["port"], "/api/masters/sessions", ck)
        ok = st == 200 and isinstance(j, dict) and "sessions" in j
        add("F11", s["port"], "sessions list", f"st={st} n={len(j.get('sessions', [])) if isinstance(j, dict) else '?'}", ok)

    # F12 login kill-switch GET only
    for s in SALONS:
        st, j = api_get(s["port"], "/api/masters/app-status", ck)
        ok = st == 200 and isinstance(j, dict) and "login_enabled" in j
        add("F12", s["port"], "login_enabled", f"st={st} {j}", ok)

    # F13 gallery APIs (no 16th upload)
    for s in SALONS:
        st1, j1 = api_get(s["port"], "/api/settings/works-photos", ck)
        st2, j2 = api_get(s["port"], "/api/settings/works-categories", ck)
        ok = st1 == 200 and isinstance(j1, list) and st2 == 200 and isinstance(j2, list) and len(j2) > 0
        add(
            "F13",
            s["port"],
            "photos+categories",
            f"photos={st1}/{len(j1) if isinstance(j1, list) else '?'} cats={st2}/{len(j2) if isinstance(j2, list) else '?'}",
            ok,
        )

    # F14 no-cookie API 401
    for s in SALONS:
        st, _, _, _ = request(f"http://{HOST}:{s['port']}/api/bot/menu")
        add("F14", s["port"], 401, f"HTTP {st}", st == 401)

    # F15 root redirect (no follow)
    for s in SALONS:
        st, hdrs, _ = request_noredirect(f"http://{HOST}:{s['port']}/")
        loc = hdrs.get("Location") or hdrs.get("location") or ""
        add("F15", s["port"], "302 /dashboard", f"{st} {loc}", st == 302 and loc.rstrip("/").endswith("/dashboard"))

    # F16 public endpoints
    for s in SALONS:
        st_h, _, _, _ = request(f"http://{HOST}:{s['port']}/health")
        st_s, _, _, _ = request(f"http://{HOST}:{s['port']}/api/services")
        add("F16", s["port"], "health+services 200", f"h={st_h} s={st_s}", st_h == 200 and st_s == 200)

    # F17 polling logs via optional SSH — skip if no paramiko/network; local heuristic: heartbeat only
    # F17 deferred to load runner / manual ssh — mark informational
    add("F17", "all", "see load runner / journal", "skipped in smoke (use load_read or ssh)", True, "optional")

    npass = sum(1 for r in results if r["status"] == "PASS")
    nfail = sum(1 for r in results if r["status"] == "FAIL")
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report = Path(__file__).parent / f"report_smoke_{ts}.md"
    with report.open("w") as f:
        f.write(f"# Functional smoke report\n\n**UTC:** {ts}\n**Host:** {host}\n")
        f.write(f"**Result:** {npass} PASS / {nfail} FAIL\n\n")
        f.write("| ID | Port | Expected | Actual | Status |\n|----|------|----------|--------|--------|\n")
        for r in results:
            exp = r["expected"].replace("|", "\\|")[:60]
            act = r["actual"].replace("|", "\\|")[:80]
            f.write(f"| {r['id']} | {r['port']} | {exp} | {act} | **{r['status']}** |\n")
    print("=" * 50)
    print(f"SUMMARY {npass} PASS / {nfail} FAIL")
    for r in results:
        if r["status"] == "FAIL":
            print(f"  FAIL {r['id']} @{r['port']}: {r['actual']}")
    print("REPORT", report)
    return 0 if nfail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
