import asyncio, aiosqlite

async def f():
    db = await aiosqlite.connect("bot_cache.db")
    
    print("=== MASTERS ===")
    cur = await db.execute("SELECT id, name, phone, telegram_id, role, is_active FROM masters")
    for r in await cur.fetchall():
        print(f"  id={r[0]} | {r[1]} | phone={r[2]} | tg_id={r[3]} | role={r[4]} | active={r[5]}")
    
    print("\n=== CLIENTS with similar phone ===")
    cur = await db.execute("SELECT telegram_id, name, phone FROM clients WHERE phone LIKE '%5040879%'")
    rows = await cur.fetchall()
    if rows:
        for r in rows:
            print(f"  tg_id={r[0]} | {r[1]} | phone={r[2]}")
    else:
        print("  No clients found with 5040879")
    
    print("\n=== ALL CLIENTS (first 20) ===")
    cur = await db.execute("SELECT telegram_id, name, phone FROM clients LIMIT 20")
    for r in await cur.fetchall():
        print(f"  tg_id={r[0]} | {r[1]} | phone={r[2]}")
    
    await db.close()

asyncio.run(f())
