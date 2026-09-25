import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

# Upload fix script
sftp = ssh.open_sftp()
sftp.put(r'C:\Users\User\mimo\kaskad-multitenant\salons\hairos\fix_director_tg_id.py', '/opt/hairos-bot/fix_director_tg_id.py')
sftp.close()
print("Fix script uploaded")

# Check hairos.studio client
script = """
import asyncio, aiosqlite
async def f():
    db = await aiosqlite.connect('bot_cache.db')
    cur = await db.execute('SELECT * FROM clients WHERE telegram_id = 7846553706')
    row = await cur.fetchone()
    if row:
        print(f'Client 7846553706: {dict(row)}')
    else:
        print('Client 7846553706 not found')
    
    # Also check if hairos.studio is the director
    cur = await db.execute('SELECT telegram_id, name, phone FROM clients WHERE name LIKE "%hairos%" OR name LIKE "%studio%"')
    rows = await cur.fetchall()
    print(f'\\nHairos-related clients: {len(rows)}')
    for r in rows:
        print(f'  tg_id={r[0]} | {r[1]} | phone={r[2]}')
    
    await db.close()
asyncio.run(f())
"""

stdin, stdout, stderr = ssh.exec_command(f'cd /opt/hairos-bot && source venv/bin/activate && python3 -c "{script}"')
print(stdout.read().decode())
err = stderr.read().decode()
if err:
    print('STDERR:', err)

ssh.close()
