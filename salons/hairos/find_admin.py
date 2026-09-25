import asyncio
import aiosqlite

async def main():
    db = await aiosqlite.connect('/opt/hairos-bot/bot_cache.db')
    
    # Check clients
    cur = await db.execute("SELECT telegram_id, name, phone FROM clients WHERE phone LIKE '%8592000%'")
    rows = await cur.fetchall()
    if rows:
        for r in rows:
            print(f"Client: id={r[0]} name={r[1]} phone={r[2]}")
    else:
        print("Phone not found in clients table")
    
    # List all clients
    cur = await db.execute("SELECT telegram_id, name, phone FROM clients")
    all_clients = await cur.fetchall()
    print(f"\nAll clients ({len(all_clients)}):")
    for r in all_clients:
        print(f"  id={r[0]} name={r[1]} phone={r[2]}")
    
    await db.close()

asyncio.run(main())
