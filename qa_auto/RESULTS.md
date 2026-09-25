# QA: функциональное + автоматизированное + нагрузочное

**Project:** `/Users/igor/mimo/kaskad-multitenant/qa_auto/`  
**Host:** `92.246.128.94` kaskad:8000, hairos:8005  
**Исключено:** usability (уже отработан ранее).

## Результаты 2026-09-23

### Функциональное — **34 PASS / 0 FAIL**
`qa_auto/report_smoke_20260923T073738Z.md`

| Блок | Покрыто |
|------|---------|
| F1–F4 | login ok/err, cookie, shared jar, все страницы+sidebar |
| F5–F6 | flags GET/PUT, toggle flip+restore |
| F7–F9 | welcome, menu CRUD+cleanup, notify flip+restore |
| F10–F13 | status/heartbeat, sessions, login_enabled, gallery |
| F14–F16 | 401 без cookie, root 302, public health/services |
| F17 | 4 сервиса active; poller без Traceback |

### Автоматизированное
```
qa_auto/smoke_api.py    # exit 0/1 → report_smoke_*.md
qa_auto/load_read.py    # read-only load → report_load_*.md
qa_auto/run_all.sh      # smoke + load
```
```bash
cd /Users/igor/mimo/kaskad-multitenant
QA_KASKAD_PW=… QA_HAIROS_PW=… bash qa_auto/run_all.sh
# load без логина (после rate-limit): QA_LOAD_TOKEN=<crm_token> python3 qa_auto/load_read.py
```

### Нагрузочное (read-only)
См. последний `qa_auto/report_load_*.md`:
- **Error rate 0%**, burst `/dashboard` **100% × 200** → hard PASS
- p50/p95 — baseline удалённого VPS (сотни мс…несколько секунд); порог hard: err&lt;1% и success≥99%
- Сервисы после прогона active, без Traceback
