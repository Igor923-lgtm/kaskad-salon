import asyncio, aiosqlite

async def fix_director():
    db = await aiosqlite.connect("bot_cache.db")
    
    # Find director's telegram_id from clients (after she shares contact)
    # Try both phone formats
    cur = await db.execute(
        "SELECT telegram_id, name, phone FROM clients WHERE phone IN (?, ?)",
        ("+375295040879", "375295040879")
    )
    client = await cur.fetchone()
    
    if client:
        tg_id = client[0]
        print(f"Found client: tg_id={tg_id}, name={client[1]}, phone={client[2]}")
        
        # Update master record
        await db.execute(
            "UPDATE masters SET telegram_id = ? WHERE phone = ?",
            (tg_id, "+375295040879")
        )
        await db.commit()
        print(f"Updated master Марина with telegram_id={tg_id}")
        
        # Verify
        cur = await db.execute("SELECT id, name, phone, telegram_id, role FROM masters WHERE phone = ?", ("+375295040879",))
        m = await cur.fetchone()
        print(f"Verify: id={m[0]}, name={m[1]}, phone={m[2]}, tg_id={m[3]}, role={m[4]}")
    else:
        print("Client with phone +375295040879 not found in clients table!")
        print("Director needs to start the bot and share her contact first.")
        
        # Show all clients for reference
        cur = await db.execute("SELECT telegram_id, name, phone FROM clients")
        print("\nAll clients:")
        for r in await cur.fetchall():
            print(f"  tg_id={r[0]} | {r[1]} | phone={r[2]}")
    
    await db.close()

asyncio.run(fix_director())
