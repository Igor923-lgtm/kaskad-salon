import asyncio
import aiosqlite

async def main():
    db = await aiosqlite.connect('/opt/hairos-bot/bot_cache.db')
    
    # Set all days as working for both masters
    for name in ['Кристина', 'Лиза']:
        for dow in range(7):  # 0=Mon to 6=Sun
            await db.execute(
                "UPDATE master_schedule SET is_day_off = 0, start_time = '10:00', end_time = '22:00' WHERE master_name = ? AND day_of_week = ?",
                (name, dow)
            )
        print(f"{name}: all days set to working 10:00-22:00")
    
    await db.commit()
    
    # Verify
    for name in ['Кристина', 'Лиза']:
        cur = await db.execute(
            "SELECT day_of_week, start_time, end_time, is_day_off FROM master_schedule WHERE master_name = ? ORDER BY day_of_week",
            (name,)
        )
        rows = await cur.fetchall()
        print(f"\n{name} schedule:")
        days_ru = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
        for r in rows:
            status = 'РАБОЧИЙ' if r[3] == 0 else 'ВЫХОДНОЙ'
            print(f"  {days_ru[r[0]]}: {r[1]}-{r[2]} {status}")
    
    await db.close()

asyncio.run(main())
