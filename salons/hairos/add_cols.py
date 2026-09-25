import asyncio
import aiosqlite

async def main():
    db = await aiosqlite.connect('/opt/hairos-bot/bot_cache.db')
    
    # Add missing columns
    try:
        await db.execute("ALTER TABLE bookings ADD COLUMN completed INTEGER DEFAULT 0")
        print("Added 'completed' column")
    except:
        print("'completed' already exists")
    
    try:
        await db.execute("ALTER TABLE bookings ADD COLUMN cancelled INTEGER DEFAULT 0")
        print("Added 'cancelled' column")
    except:
        print("'cancelled' already exists")
    
    try:
        await db.execute("ALTER TABLE bookings ADD COLUMN phone TEXT DEFAULT ''")
        print("Added 'phone' column")
    except:
        print("'phone' already exists")
    
    await db.commit()
    await db.close()
    print("Done!")

asyncio.run(main())
