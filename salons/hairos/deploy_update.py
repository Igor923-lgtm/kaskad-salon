import paramiko
import os

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)
sftp = ssh.open_sftp()

# 1. Upload modified code files
files = [
    (r'C:\Users\User\mimo\kaskad-multitenant\bot.py', '/opt/hairos-bot/bot.py'),
    (r'C:\Users\User\mimo\kaskad-multitenant\salons\hairos\price_data.py', '/opt/hairos-bot/price_data.py'),
]

for local, remote in files:
    sftp.put(local, remote)
    print(f"OK: {os.path.basename(local)} -> {remote.split('/')[-1]}")

# 2. Create works_photos subdirectories
dirs = [
    '/opt/hairos-bot/works_photos/zagushchenie',
    '/opt/hairos-bot/works_photos/narashchivanie',
    '/opt/hairos-bot/works_photos/smp',
    '/opt/hairos-bot/works_photos/botoks_keratin',
]
for d in dirs:
    stdin, stdout, stderr = ssh.exec_command(f'mkdir -p {d}')
    stdout.channel.recv_exit_status()
    print(f"DIR: {d}")

# 3. Upload category photos
photos = [
    (r'C:\Users\User\Desktop\Загущение.png', '/opt/hairos-bot/works_photos/zagushchenie/photo1.png'),
    (r'C:\Users\User\Desktop\наращивание.PNG', '/opt/hairos-bot/works_photos/narashchivanie/photo1.png'),
    (r'C:\Users\User\Desktop\трихопигментация (SMP).PNG', '/opt/hairos-bot/works_photos/smp/photo1.png'),
    (r'C:\Users\User\Desktop\ботокс-кератин.jpg', '/opt/hairos-bot/works_photos/botoks_keratin/photo1.jpg'),
]

for local, remote in photos:
    sftp.put(local, remote)
    print(f"PHOTO: {os.path.basename(local)} -> {remote.split('/')[-2]}/{remote.split('/')[-1]}")

sftp.close()

# 4. Update masters in database
update_masters_script = '''
import asyncio, aiosqlite

async def update():
    db = await aiosqlite.connect("bot_cache.db")
    
    # Delete old masters
    await db.execute("DELETE FROM masters")
    
    # Insert new masters
    masters = [
        ("Кристина", "Мастер по наращиванию волос", "", 
         "Капсульное наращивание волос\\nКоррекция наращивания", "0"),
        ("Лиза", "Мастер по восстановлению волос", "",
         "Кератиновое восстановление\\nБотокс для волос\\nХолодное восстановление\\nТотальная реконструкция", "1"),
        ("Марина", "Основатель студии", "",
         "Капсульное/Голливудское наращивание волос\\nТрихопигментация (SMP)\\nОбучение", "0,2"),
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
'''

stdin, stdout, stderr = ssh.exec_command(f'cd /opt/hairos-bot && source venv/bin/activate && python3 -c "{update_masters_script}"')
print("\n=== Updating masters ===")
print(stdout.read().decode())
err = stderr.read().decode()
if err:
    print("STDERR:", err)

# 5. Restart services
stdin, stdout, stderr = ssh.exec_command('systemctl restart hairos-bot hairos-polling')
stdout.channel.recv_exit_status()
print("\nServices restarted!")

import time
time.sleep(3)

# 6. Health check
stdin, stdout, stderr = ssh.exec_command('curl -s http://localhost:8005/health')
print(f"Health: {stdout.read().decode().strip()}")

stdin, stdout, stderr = ssh.exec_command('systemctl is-active hairos-bot hairos-polling')
print(f"Services: {stdout.read().decode().strip()}")

ssh.close()
print("\nDeploy complete!")
