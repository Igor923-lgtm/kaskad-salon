import asyncio
import aiosqlite

async def main():
    db = await aiosqlite.connect('/opt/hairos-bot/bot_cache.db')
    
    # Check Kristina's date schedule for 24.08.2026
    cur = await db.execute(
        "SELECT * FROM master_date_schedule WHERE master_name = 'Кристина' AND date = '2026-08-24'"
    )
    row = await cur.fetchone()
    if row:
        print(f"Date schedule: {row}")
    else:
        print("No date schedule for 24.08.2026")
    
    # Check Kristina's weekly schedule
    cur = await db.execute(
        "SELECT * FROM master_schedule WHERE master_name = 'Кристина' ORDER BY day_of_week"
    )
    rows = await cur.fetchall()
    print(f"\nWeekly schedule ({len(rows)} entries):")
    for r in rows:
        print(f"  dow={r[2]} start={r[3]} end={r[4]} off={r[5]} selected={r[6]}")
    
    # Check all date schedules for Kristina
    cur = await db.execute(
        "SELECT * FROM master_date_schedule WHERE master_name = 'Кристина' ORDER BY date"
    )
    rows = await cur.fetchall()
    print(f"\nAll date schedules ({len(rows)} entries):")
    for r in rows:
        print(f"  date={r[2]} slots={r[3]} off={r[4]}")
    
    await db.close()

asyncio.run(main())
