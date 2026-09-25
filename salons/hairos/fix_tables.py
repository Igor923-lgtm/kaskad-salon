import asyncio
import aiosqlite

async def main():
    db = await aiosqlite.connect('/opt/hairos-bot/bot_cache.db')
    cur = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    rows = await cur.fetchall()
    print("Tables in hairos DB:")
    for r in rows:
        print(f"  {r[0]}")
    
    # Check if transactions table exists
    tables = [r[0] for r in rows]
    if 'transactions' not in tables:
        print("\n'transactions' table MISSING - creating it...")
        await db.execute('''CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_id INTEGER DEFAULT 0,
            master_name TEXT DEFAULT '',
            service_name TEXT DEFAULT '',
            amount REAL DEFAULT 0,
            payment_type TEXT DEFAULT 'cash',
            created_at TEXT DEFAULT (datetime('now'))
        )''')
        await db.commit()
        print("transactions table created!")
    
    if 'client_notes' not in tables:
        print("\n'client_notes' table MISSING - creating it...")
        await db.execute('''CREATE TABLE IF NOT EXISTS client_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_telegram_id INTEGER,
            author TEXT DEFAULT '',
            text TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        )''')
        await db.commit()
        print("client_notes table created!")
    
    if 'reviews' not in tables:
        print("\n'reviews' table MISSING - creating it...")
        await db.execute('''CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            master_name TEXT,
            client_name TEXT,
            score INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        )''')
        await db.commit()
        print("reviews table created!")
    
    if 'salon_settings' not in tables:
        print("\n'salon_settings' table MISSING - creating it...")
        await db.execute('''CREATE TABLE IF NOT EXISTS salon_settings (
            key TEXT PRIMARY KEY,
            value TEXT DEFAULT ''
        )''')
        await db.commit()
        print("salon_settings table created!")
    
    if 'master_sessions' not in tables:
        print("\n'master_sessions' table MISSING - creating it...")
        await db.execute('''CREATE TABLE IF NOT EXISTS master_sessions (
            token TEXT PRIMARY KEY,
            master_id INTEGER,
            master_name TEXT,
            telegram_id INTEGER,
            expires TEXT
        )''')
        await db.commit()
        print("master_sessions table created!")
    
    if 'master_date_schedule' not in tables:
        print("\n'master_date_schedule' table MISSING - creating it...")
        await db.execute('''CREATE TABLE IF NOT EXISTS master_date_schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            master_name TEXT NOT NULL,
            date TEXT NOT NULL,
            time_slots TEXT DEFAULT '',
            is_day_off INTEGER DEFAULT 0,
            UNIQUE(master_name, date)
        )''')
        await db.commit()
        print("master_date_schedule table created!")
    
    await db.close()
    print("\nAll tables verified!")

asyncio.run(main())
