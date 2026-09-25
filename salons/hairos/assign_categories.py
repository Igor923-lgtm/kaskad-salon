import asyncio
import aiosqlite

async def main():
    db = await aiosqlite.connect('/opt/hairos-bot/bot_cache.db')
    
    # Kristina - section 0 (Наращивание волос)
    await db.execute("UPDATE masters SET categories = '0' WHERE name = 'Кристина'")
    print('Кристина -> категории: 0 (Наращивание)')
    
    # Liza - sections 1,2,3 (Восстановление, Уходовые, Выпрямление)
    await db.execute("UPDATE masters SET categories = '1,2,3' WHERE name = 'Лиза'")
    print('Лиза -> категории: 1,2,3 (Восстановление, Уходовые, Выпрямление)')
    
    await db.commit()
    
    # Verify
    cur = await db.execute('SELECT name, categories FROM masters WHERE is_active = 1')
    for r in await cur.fetchall():
        print(f'  {r[0]}: categories={r[1]}')
    
    await db.close()

asyncio.run(main())
