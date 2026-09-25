import asyncio, aiosqlite

async def update():
    db = await aiosqlite.connect("bot_cache.db")
    
    # Delete old masters
    await db.execute("DELETE FROM masters")
    
    # Insert new masters
    masters = [
        ("Кристина", "Мастер по наращиванию волос", "", 
         "Капсульное наращивание волос\nКоррекция наращивания", "0"),
        ("Лиза", "Мастер по восстановлению волос", "",
         "Кератиновое восстановление\nБотокс для волос\nХолодное восстановление\nТотальная реконструкция", "1"),
        ("Марина", "Основатель студии", "",
         "Капсульное/Голливудское наращивание\nТрихопигментация SMP\nОбучение", "0,2"),
    ]
    
    for name, spec, photo, desc, cats in masters:
        await db.execute(
            "INSERT INTO masters (name, specialization, photo_file_id, description, categories) VALUES (?, ?, ?, ?, ?)",
            (name, spec, photo, desc, cats)
        )
    
    await db.commit()
    print("Masters updated!")
    
    # Verify
    cur = await db.execute("SELECT name, specialization, categories FROM masters")
    rows = await cur.fetchall()
    for r in rows:
        print(f"  {r[0]} | {r[1]} | cats={r[2]}")
    
    await db.close()

asyncio.run(update())
