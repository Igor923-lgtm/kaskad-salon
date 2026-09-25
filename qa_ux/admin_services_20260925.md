# Тест админки ЦРМ + создание услуг — 2026-09-25

**Стенд:** локальный uvicorn `:8765` · CRM login form · Playwright 390×844  
**Итог: API+страницы 18/18 · UI 16/16 · pytest 31**

## Админка (страницы, cookie)
| Страница | Результат |
|----------|-----------|
| `/dashboard` | 200, Дашборд |
| `/services` | 200, `categoriesList` |
| `/masters` `/clients` `/finance` `/settings` `/bookings` | 200 |
| Login → dashboard | redirect OK |

## Services CRUD (API)
| Шаг | Результат |
|-----|-----------|
| GET list/categories/grouped | 154 / 26 / 26 |
| **POST** создать | id, 200 |
| Виден в списке | ✓ |
| **PUT** имя/цена/длительность | ✓ видно |
| Без cookie → POST | **401** |
| **DELETE** | ok · исчез |
| DELETE missing | **404** |

## UI (Playwright)
| Шаг | Результат |
|-----|-----------|
| Login → dashboard | ✓ |
| `/services` категории (54 header) | ✓ |
| **+ Категория** «E2E Админ Раздел» | modal + сохранена |
| **Новая услуга** modal | открыт, без prompt |
| Заполнить + Сохранить | «E2E UI Услуга» после reload |
| /dashboard /masters /clients /finance | sidebar есть |
| alert/prompt/confirm | **0** · pageerror **0** |

Скриншоты: `qa_ux/run_admin_svc_20260925/0*.png` · JSON: `api_results.json`, `ui_results.json`

## Чистка
U-услуга и E2E-категория удалены после теста (API DELETE).

## Прод
Не трогали (записи только локально).
