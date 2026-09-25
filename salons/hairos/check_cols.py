import asyncio
import aiosqlite

async def main():
    db = await aiosqlite.connect('/opt/hairos-bot/bot_cache.db')
    cur = await db.execute("PRAGMA table_info(bookings)")
    cols = await cur.fetchall()
    print("bookings columns:")
    for c in cols:
        print(f"  {c[1]} ({c[2]})")
    await db.close()

asyncio.run(main())
