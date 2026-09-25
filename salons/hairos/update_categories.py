import asyncio
import aiosqlite

async def main():
    db = await aiosqlite.connect('/opt/hairos-bot/bot_cache.db')
    
    # Кристина - section 0 (Наращивание волос)
    await db.execute("UPDATE masters SET categories = '0' WHERE name = 'Кристина'")
    print("Кристина -> категории: 0 (Наращивание)")
    
    # Лиза - section 1 (Восстановление волос)
    await db.execute("UPDATE masters SET categories = '1' WHERE name = 'Лиза'")
    print("Лиза -> категории: 1 (Восстановление)")
    
    await db.commit()
    
    # Verify
    cur = await db.execute('SELECT name, categories FROM masters WHERE is_active = 1')
    for r in await cur.fetchall():
        print(f"  {r[0]}: categories={r[1]}")
    
    await db.close()

asyncio.run(main())
