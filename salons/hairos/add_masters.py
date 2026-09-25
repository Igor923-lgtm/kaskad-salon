import paramiko
import json

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

# Add masters via Python script on server
script = """
import asyncio
import aiosqlite

async def main():
    db = await aiosqlite.connect('/opt/hairos-bot/bot_cache.db')
    
    # Create masters table if not exists
    await db.execute('''CREATE TABLE IF NOT EXISTS masters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        specialization TEXT DEFAULT '',
        description TEXT DEFAULT '',
        categories TEXT DEFAULT '',
        photo_file_id TEXT DEFAULT '',
        phone TEXT DEFAULT '',
        telegram_id INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1,
        commission_percent INTEGER DEFAULT 50
    )''')
    
    # Add Kristina
    await db.execute(
        'INSERT INTO masters (name, specialization, description, phone) VALUES (?,?,?,?)',
        ('Кристина', 'Мастер по наращиванию волос', 'Капсульное наращивание волос, коррекция волос', '+37295949109')
    )
    print('Кристина добавлена')
    
    # Add Liza
    await db.execute(
        'INSERT INTO masters (name, specialization, description, phone) VALUES (?,?,?,?)',
        ('Лиза', 'Мастер по восстановлению волос', 'Кератиновое восстановление, ботокс, холодное восстановление, тотальная реконструкция', '+375333077592')
    )
    print('Лиза добавлена')
    
    await db.commit()
    
    # Verify
    cur = await db.execute('SELECT id, name, phone FROM masters WHERE is_active = 1')
    rows = await cur.fetchall()
    for r in rows:
        print(f'  id={r[0]} | {r[1]} | {r[2]}')
    
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
