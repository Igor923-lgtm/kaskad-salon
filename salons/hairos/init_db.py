import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

script = """
import asyncio
import aiosqlite

async def main():
    db = await aiosqlite.connect('/opt/hairos-bot/bot_cache.db')
    
    # Create master_schedule table
    await db.execute('''CREATE TABLE IF NOT EXISTS master_schedule (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        master_name TEXT NOT NULL,
        day_of_week INTEGER NOT NULL,
        start_time TEXT DEFAULT '10:00',
        end_time TEXT DEFAULT '21:00',
        is_day_off INTEGER DEFAULT 0,
        selected_hours TEXT DEFAULT '',
        UNIQUE(master_name, day_of_week)
    )''')
    
    # Create master_date_schedule table
    await db.execute('''CREATE TABLE IF NOT EXISTS master_date_schedule (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        master_name TEXT NOT NULL,
        date TEXT NOT NULL,
        time_slots TEXT DEFAULT '',
        is_day_off INTEGER DEFAULT 0,
        UNIQUE(master_name, date)
    )''')
    
    # Create bookings table
    await db.execute('''CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        master_name TEXT NOT NULL,
        date TEXT NOT NULL,
        time TEXT NOT NULL,
        client_name TEXT DEFAULT '',
        phone TEXT DEFAULT '',
        telegram_id INTEGER DEFAULT 0,
        service_name TEXT DEFAULT '',
        price TEXT DEFAULT '',
        confirmed INTEGER DEFAULT 0,
        completed INTEGER DEFAULT 0,
        cancelled INTEGER DEFAULT 0,
        reminder_sent INTEGER DEFAULT 0,
        reminder_2h_sent INTEGER DEFAULT 0,
        reminder_repeat_sent INTEGER DEFAULT 0,
        review_sent INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now'))
    )''')
    
    # Create clients table
    await db.execute('''CREATE TABLE IF NOT EXISTS clients (
        telegram_id INTEGER PRIMARY KEY,
        name TEXT DEFAULT '',
        phone TEXT DEFAULT '',
        birthday TEXT DEFAULT '',
        client_type TEXT DEFAULT 'lead',
        discount_percent INTEGER DEFAULT 0,
        visit_count INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )''')
    
    # Create other tables
    await db.execute('''CREATE TABLE IF NOT EXISTS client_notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_telegram_id INTEGER,
        author TEXT DEFAULT '',
        text TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now'))
    )''')
    
    await db.execute('''CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        master_name TEXT,
        client_name TEXT,
        score INTEGER,
        created_at TEXT DEFAULT (datetime('now'))
    )''')
    
    await db.execute('''CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        booking_id INTEGER DEFAULT 0,
        master_name TEXT DEFAULT '',
        service_name TEXT DEFAULT '',
        amount REAL DEFAULT 0,
        payment_type TEXT DEFAULT 'cash',
        created_at TEXT DEFAULT (datetime('now'))
    )''')
    
    await db.execute('''CREATE TABLE IF NOT EXISTS salon_settings (
        key TEXT PRIMARY KEY,
        value TEXT DEFAULT ''
    )''')
    
    await db.execute('''CREATE TABLE IF NOT EXISTS master_sessions (
        token TEXT PRIMARY KEY,
        master_id INTEGER,
        master_name TEXT,
        telegram_id INTEGER,
        expires TEXT
    )''')
    
    # Add default schedule for both masters (Mon-Sat 10-21, Sun off)
    for name in ['Кристина', 'Лиза']:
        for dow in range(6):  # Mon-Sat
            await db.execute(
                'INSERT OR IGNORE INTO master_schedule (master_name, day_of_week, start_time, end_time, is_day_off) VALUES (?,?,?,?,?)',
                (name, dow, '10:00', '21:00', 0)
            )
        # Sunday off
        await db.execute(
            'INSERT OR IGNORE INTO master_schedule (master_name, day_of_week, start_time, end_time, is_day_off) VALUES (?,?,?,?,?)',
            (name, 6, '10:00', '21:00', 1)
        )
    
    await db.commit()
    print('All tables created, schedule added')
    
    # Verify
    cur = await db.execute('SELECT master_name, day_of_week, is_day_off FROM master_schedule ORDER BY master_name, day_of_week')
    rows = await cur.fetchall()
    for r in rows:
        print(f'  {r[0]} | dow={r[1]} | off={r[2]}')
    
    await db.close()

asyncio.run(main())
"""

stdin, stdout, stderr = ssh.exec_command(f'cd /opt/hairos-bot && source venv/bin/activate && python3 -c "{script}"')
out = stdout.read().decode()
err = stderr.read().decode()
print(out)
if err:
    print('STDERR:', err)

ssh.close()
print('Done!')
