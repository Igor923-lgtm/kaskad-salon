import asyncio
import aiosqlite

async def main():
    db = await aiosqlite.connect('/opt/hairos-bot/bot_cache.db')
    
    # Check master_sessions table
    cur = await db.execute("SELECT * FROM master_sessions")
    rows = await cur.fetchall()
    print(f"Active sessions: {len(rows)}")
    for r in rows:
        print(f"  token={r[0][:10]}... master={r[2]} tg={r[3]} expires={r[4]}")
    
    # Check masters table
    cur = await db.execute("SELECT id, name, phone, telegram_id FROM masters WHERE is_active = 1")
    rows = await cur.fetchall()
    print(f"\nMasters:")
    for r in rows:
        print(f"  id={r[0]} name={r[1]} phone={r[2]} tg={r[3]}")
    
    await db.close()

asyncio.run(main())
