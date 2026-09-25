import asyncio
import aiosqlite

async def main():
    db = await aiosqlite.connect('/opt/hairos-bot/bot_cache.db')
    
    # Check Kristina's weekly schedule for Monday (dow=0)
    cur = await db.execute(
        "SELECT * FROM master_schedule WHERE master_name = 'Кристина' AND day_of_week = 0"
    )
    row = await cur.fetchone()
    print(f"Kristina Monday weekly: {row}")
    
    # Check if there's a date schedule for 24.08.2026
    cur = await db.execute(
        "SELECT * FROM master_date_schedule WHERE master_name = 'Кристина' AND date = '2026-08-24'"
    )
    row = await cur.fetchone()
    print(f"Kristina 24.08 date schedule: {row}")
    
    # Check the set_date_schedule function exists in db.py
    cur = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='master_date_schedule'")
    row = await cur.fetchone()
    print(f"master_date_schedule table: {'exists' if row else 'MISSING'}")
    
    await db.close()

asyncio.run(main())
