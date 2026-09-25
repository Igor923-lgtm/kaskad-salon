# UX регресс — 2026-09-25

**Scope:** вход мастера · дашборд · ЦРМ (settings, schedule, CSV) после дня правок (орг-режим, выходные, CSV, RU-тексты, пинч-zoom).

**Environment:** local uvicorn `:8765` (SALON_ID=kaskad, CRM test pass) + Playwright 390×844.

## Итог: **24+ / PASS** (1 env-сбой локальной БД → устранён db.init)

| # | Проверка | Результат |
|---|----------|-----------|
| A1 | viewport без `user-scalable`, есть `maximum-scale` | PASS |
| A2 | `#phone` `inputmode=tel` | PASS |
| A3 | нет `touchend` на login | PASS |
| A4 | junk localStorage, без cookie → **остаёмся** на форме, токен очищен | PASS |
| A5 | label tap → focus phone | PASS |
| B1 | dashboard грузится · `gesturestart` (анти-пинч) | PASS |
| B2 | Мастера → «+» → **модалка**, prompt=0 / alert=0 | PASS |
| C1 | Settings: «Режим работы» + hint | PASS |
| C2 | Schedule: helper «Колонки», CSS `.dayoff`, `exclude_admins=1` | PASS |
| C3 | `GET /api/schedule/dayoff` → `{}` (объект, не массив) | PASS |
| C4 | exclude_admins скрывает АДМИН | PASS |
| C5 | CSV KPI: **BOM `efbbbf`**, `Показатель;Значение`, `charset=utf-8` | PASS* |
| C6 | bookings без 500 (колонка booking_type) | PASS после `db.init` + guard |

\* Локально KPI падал 500 из-за **устаревшей** схемы (`duration_minutes`/`booking_type`); **прод уже проверен ранее**. Добавлен guard в `list_bookings` если нет `booking_type`.

## Артефакты
- `qa_ux/run_regress_20260925/regress_results.json`
- Скрины `01_login` … `07_dashboard.png`

## Git
- Root commit **`8e4af22`** — `feat: initial import` (209 files, 31877 lines)  
- Secrets: `.env*`, `deploy_settings.py`, `works_photos/`, `*.db` — **не в коммите**  
- `deploy_settings.example.py` — шаблон без пароля  

## Остатки
- Регресс **не** гонялся против **prod** шлюза (только локально + раньше prod smoke)  
- `bookings_grouped` на старой схеме без `booking_type` — тот же guard при желании  
