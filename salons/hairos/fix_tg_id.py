import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

script = """
import asyncio, aiosqlite
async def main():
    db = await aiosqlite.connect('bot_cache.db')
    await db.execute('UPDATE masters SET telegram_id = 294308582 WHERE phone = ?', ('+375298592000',))
    await db.commit()
    cur = await db.execute('SELECT id, name, phone, role, telegram_id FROM masters WHERE phone = ?', ('+375298592000',))
    row = await cur.fetchone()
    print(f'id={row[0]}, name={row[1]}, phone={row[2]}, role={row[3]}, tg_id={row[4]}')
    await db.close()
asyncio.run(main())
"""

# Hairos
stdin, stdout, stderr = ssh.exec_command(f'cd /opt/hairos-bot && source venv/bin/activate && python3 -c "{script}"')
print("Hairos:", stdout.read().decode().strip())

# Kaskad
stdin, stdout, stderr = ssh.exec_command(f'cd /opt/telegram-bot && source venv/bin/activate && python3 -c "{script}"')
print("Kaskad:", stdout.read().decode().strip())

# Restart
stdin, stdout, stderr = ssh.exec_command('systemctl restart hairos-bot hairos-polling crm-api telegram-bot')
stdout.channel.recv_exit_status()
print("Services restarted")

import time
time.sleep(3)

stdin, stdout, stderr = ssh.exec_command('curl -s http://localhost:8005/health')
print(f"Hairos: {stdout.read().decode().strip()}")
stdin, stdout, stderr = ssh.exec_command('curl -s http://localhost:8000/health')
print(f"Kaskad: {stdout.read().decode().strip()}")

ssh.close()
print("Done!")
