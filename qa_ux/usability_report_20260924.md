# Usability report — CRM (ЦРМ)

**Date:** 2026-09-24  
**Scope:** CRM sidebar pages only (not bot / widget / master app)  
**Baseline:** `qa_ux/ux_report_20260923.md` (0 P0 / 3 P1 / 4 P2)

## Method

1. Code + template audit vs prior report (titles, prompt/alert, modals, empty states).
2. HTTP login E2E on server: kaskad2026 / hairos2026 → dashboard 200.
3. **Playwright browser walk (Python, headless Chromium):** desktop 1280 + mobile 390, both salons — full page set with screenshots.

## Browser walk results (2026-09-24)

**Summary: 0 P0/P1 open · ovX = 0 on all measured pages · titles all contain salon name.**

| Check | kaskad | hairos |
|-------|--------|--------|
| Login → dashboard | PASS | PASS |
| 10 CRM pages, no login wall | PASS | PASS |
| ovX desktop | **0** all pages | **0** all pages |
| ovX mobile @390 dashboard/settings/schedule | **0** | **0** |
| titles | `… — Коворкинг` | `… — Hairos Studio` |

Raw: `qa_ux/run_20260924/walk_results.json`  
Screenshots: `qa_ux/run_20260924/kaskad/*.png`, `qa_ux/run_20260924/hairos/*.png` (~17 each).

## Journeys

| Journey | Result | Notes |
|---------|--------|-------|
| Login form + correct password | PASS | both salons, browser + HTTP |
| Nav 10 pages | PASS | titles `{{salon_name}}` |
| Service CRUD + duration | PASS | modal `svcDuration` |
| Booking create duration hint | **FIXED** | `schedule.html` «≈ N мин» |
| Booking create success | **FIXED** | toast |
| Price edit / add user / CSV | **FIXED** | modals, no `prompt` |
| Settings buffer / KPI | PASS | toast + loadKpi |
| Settings photo gallery | ALREADY OK | link only to Bot |
| Mobile overflow P1 (20260923) | **CLOSED** | ovX=0 @390 |

## Findings fixed this pass

| Sev | Item | Files |
|-----|------|--------|
| **P0** | POST `/login` blocked by auth middleware | `api.py` |
| P3 | prompt add user / price / CSV | users, bookings, clients |
| P3 | alert on booking create | schedule → toast |
| P3 | no duration hint on create booking | schedule |
| P3 | category placeholder | masters |

## Remaining (optional)

| Sev | Item |
|-----|------|
| P3 | toast not on services/masters saves |
| P3 | pagination clients/transactions |
| P3 | friendly message on login 429 |

## Verification checklist

- [x] No `prompt(` in users/bookings/clients/schedule  
- [x] JS `node --check` OK  
- [x] settings buffer + duration hint  
- [x] **Browser walk both prod CRM** (ovX=0, screenshots)  
- [x] pytest 22 passed  

## Artifacts

- Prior: `qa_ux/kaskad/*.png`, `qa_ux/hairos/*.png`
- This: `qa_ux/usability_report_20260924.md`, `qa_ux/run_20260924/`

