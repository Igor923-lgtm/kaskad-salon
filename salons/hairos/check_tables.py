import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

# Check if transactions table exists
stdin, stdout, stderr = ssh.exec_command(
    "cd /opt/hairos-bot && source venv/bin/activate && python3 -c \""
    "import asyncio, aiosqlite; "
    "async def main(): "
    "  db = await aiosqlite.connect('bot_cache.db'); "
    "  cur = await db.execute(\\\"SELECT name FROM sqlite_master WHERE type='table'\\\"); "
    "  rows = await cur.fetchall(); "
    "  [print(r[0]) for r in rows]; "
    "  await db.close(); "
    "asyncio.run(main())\""
)
print("Tables:", stdout.read().decode())

ssh.close()
