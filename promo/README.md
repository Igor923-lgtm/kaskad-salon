# Promo package — README

## Что внутри

```
promo/
  script/          сценарий, storyboard (md/tsv/html)
  frames/          PNG-кадры из qa_ux + логотип
  captions/        SRT (рус.) ролики A и B
  video/           сырые записи Playwright (.webm)
  outreach/        шаблон WhatsApp
```

## Как собрать финальный MP4 (3–4 дня, по плану)

1. **Самый быстрый путь:** откройте `script/storyboard_A.html` в браузере, **запишите экран** (⌘⇧5) 70–75 сек → получите готовый ролик A. Субтитры уже в кадре.
2. **Полный путь:** импортируйте `video/*.webm` + `frames/*.png` в CapCut/iMovie, наложите `captions/promo_A_ru.srt`, музыка YouTube Audio Library, экспорт 1080p + 9:16.
3. **Ролик B:** `video/promo_B_widget.webm` + SRT B (30–40 с) для Reels.

## Сырые записи (сегодня)

| Файл | Что |
|------|-----|
| `video/promo_A_crm.webm` | ЦРМ: services → schedule → bookings → analytics → settings |
| `video/promo_B_widget.webm` | Онлайн-виджет |
| `video/promo_A_master_mobile.webm` | Приложение мастеров 390×844 |

## Готово из плана (День 1)

- [x] Референс-кадры (10+ PNG)  
- [x] Сценарий A + B + VO  
- [x] SRT субтитры  
- [x] Логотип  
- [x] Outreach-шаблон WhatsApp  
- [x] Сырые UI-видео (Playwright)  
- [x] HTML-storyboard для быстрой записи экрана  

## Осталось (ручное, 1 день)

- [ ] Экспорт MP4 (CapCut / запись storyboard)  
- [ ] Музыка из бесплатной библиотеки  
- [ ] YouTube unlisted + ссылка в WhatsApp  
- [ ] QC: без паролей, CTA в конце  
