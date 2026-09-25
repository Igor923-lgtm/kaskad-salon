import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

phone = '+375298592000'

# === HAIROS ===
print("=== HAIROS ===")
# Check if master exists
stdin, stdout, stderr = ssh.exec_command(f"cd /opt/hairos-bot && source venv/bin/activate && python3 -c \"import asyncio,aiosqlite; exec(\\\"import asyncio\\nasync def f():\\n    db=await aiosqlite.connect('bot_cache.db')\\n    cur=await db.execute('SELECT id,name,role FROM masters WHERE phone=?',('{phone}',))\\n    r=await cur.fetchone()\\n    print('Master:',r)\\n    await db.close()\\nasyncio.run(f())\\\")\"")
print(stdout.read().decode())
print(stderr.read().decode())

# Update or insert
script = f"""
import asyncio, aiosqlite
async def main():
    db = await aiosqlite.connect('bot_cache.db')
    cur = await db.execute('SELECT id FROM masters WHERE phone = ?', ('{phone}',))
    row = await cur.fetchone()
    if row:
        await db.execute('UPDATE masters SET role = ? WHERE id = ?', ('super_admin', row[0]))
        print(f'Updated master id={{row[0]}} to super_admin')
    else:
        await db.execute('INSERT INTO masters (name, phone, role, is_active) VALUES (?, ?, ?, 1)', ('Суперадмин', '{phone}', 'super_admin'))
        print('Inserted new super_admin')
    await db.commit()
    # Verify
    cur = await db.execute('SELECT id, name, phone, role FROM masters WHERE phone = ?', ('{phone}',))
    row = await cur.fetchone()
    print(f'Verify: id={{row[0]}}, name={{row[1]}}, phone={{row[2]}}, role={{row[3]}}')
    await db.close()
asyncio.run(main())
"""
stdin, stdout, stderr = ssh.exec_command(f'cd /opt/hairos-bot && source venv/bin/activate && python3 -c "{script}"')
print("Hairos result:", stdout.read().decode())
if stderr.read().decode():
    print("Hairos stderr:", stderr.read().decode())

# === KASKAD ===
print("\n=== KASKAD ===")
stdin, stdout, stderr = ssh.exec_command(f'cd /opt/telegram-bot && source venv/bin/activate && python3 -c "{script}"')
print("Kaskad result:", stdout.read().decode())
if stderr.read().decode():
    print("Kaskad stderr:", stderr.read().decode())

# Restart services
stdin, stdout, stderr = ssh.exec_command('systemctl restart hairos-bot hairos-polling crm-api telegram-bot')
stdout.channel.recv_exit_status()
print("\nAll services restarted")

import time
time.sleep(3)

# Health checks
stdin, stdout, stderr = ssh.exec_command('curl -s http://localhost:8005/health')
print(f"Hairos: {stdout.read().decode().strip()}")
stdin, stdout, stderr = ssh.exec_command('curl -s http://localhost:8000/health')
print(f"Kaskad: {stdout.read().decode().strip()}")

ssh.close()
print("\nDone!")
