# Usability — приложение мастера · 2026-09-24

**Scope:** `/master` login + `/master/dashboard` (master app)  
**Viewport:** 390×844 (mobile, touch)  
**Artifacts:** `qa_ux/run_master_20260924/` (`walk_results.json`, 01–11 PNG)  
**Method:** Playwright sequential + API mocks (локальная БД kaskad без `booking_type` — схема отличается от прода)

## Итог: **19 / 19 PASS** · prompt=0 · alert=0 · confirm=0 · overflow=0

| # | Сценарий | Результат |
|---|----------|-----------|
| 1 | `/master` — вход, поле телефона | PASS |
| 2 | Dashboard (cookie `master_session` + localStorage) | PASS |
| 3 | Сегодня: карточки записей (2), нет error-state | PASS |
| 4 | Переключатель Сегодня/Неделя | PASS |
| 5 | Клиенты | PASS |
| 6 | Календарь | PASS |
| 7 | Ещё → Мастера | PASS |
| 8 | **+ Добавить мастера → модалка** (не prompt) | PASS |
| 9 | Модалка закрывается кнопкой «Отмена» | PASS |
| 10 | Услуги / Финансы | PASS |
| 11 | Ещё → Пользователи (admin) | PASS |
| 12 | **Модалка пользователя** (не prompt) | PASS |
| 13 | Горизонтальный overflow | PASS (delta=0) |
| 14 | Нативные prompt/alert диалоги | PASS (0) |

## Закрыто (этот заход)

### P0
- [x] Мастера CRUD: `prompt()` цепочка → **`#masterModal`**
- [x] Пользователи: `prompt()` → **`#userModal`** (имя/телефон/роль)
- [x] **Серверная auth** `/master/dashboard`: cookie `master_session` или CRM cookie → иначе **302 /master**  
  - verify OTP ставит httponly cookie  
  - smoke: no-cookie **302**, cookie **200**

### P1
- [x] `showToast` + `.saved` (bottom 80px, z 1200) вместо alert  
- [x] `openConfirmModal` вместо confirm (отмена записи, удаление, рассылка)  
- [x] Мёртвый «Пользователи» → пункт в «Ещё» (admin)  
- [x] Дубли id `tabTodayBtn` → `dayToggleHtml(active)`  
- [x] ✅/❌ → Font Awesome + aria-label + 44px  
- [x] **z-index:** `.modal-overlay` 200 → **1100** (был **ниже** bottom-nav 1000 — футер модалки не кликался)

### P2
- [x] `user-scalable=no` убран  
- [x] Empty states с иконкой (`emptyState()`)  
- [x] Toggle Сегодня/Неделя min-height 44px  

## Проверки кода
- `grep prompt(` master_dashboard = **0**  
- `grep alert(|confirm(` = **0**  
- `py_compile api.py` OK · **pytest 23 passed**  
- Auth smoke: `/master/dashboard` → 302 без cookie / 200 с cookie  

## Остатки / не в скоупе
- Реальный OTP через Telegram (в тесте mock-сессия)  
- Локальная БД kaskad несовместима с `booking_type` в `/api/master/today` — **только для dev-walk**; прод обновлён ранее  
- Деплой шаблонов + api.py + style_v6.css на kaskad/hairos — **не выполнен в этом шаге**  
- `masters_app.html` (CRM sessions) — не гонялся  

## Скриншоты
`qa_ux/run_master_20260924/01_login.png` … `11_user_modal.png`
