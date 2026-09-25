import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)
sftp = ssh.open_sftp()
with sftp.open('/opt/hairos-bot/fix_marina_cats.py', 'w') as f:
    f.write("import sqlite3\n")
    f.write("db = sqlite3.connect('bot_cache.db')\n")
    f.write("cur = db.cursor()\n")
    f.write("cur.execute(\"UPDATE masters SET categories='0,1,2,3' WHERE name='Марина'\")\n")
    f.write("print(f'Updated: {cur.rowcount} rows')\n")
    f.write("db.commit()\n")
    f.write("cur.execute('SELECT id, name, categories FROM masters')\n")
    f.write("for r in cur.fetchall(): print(r)\n")
    f.write("db.close()\n")
sftp.close()
# Upload price_data.py
sftp = ssh.open_sftp()
sftp.put(r'C:\Users\User\mimo\kaskad-multitenant\salons\hairos\price_data.py', '/opt/hairos-bot/price_data.py')
sftp.close()
# Run fix
stdin, stdout, stderr = ssh.exec_command('cd /opt/hairos-bot && source venv/bin/activate && python3 fix_marina_cats.py 2>&1')
print(stdout.read().decode())
# Restart
stdin, stdout, stderr = ssh.exec_command('systemctl restart hairos-polling')
stdout.channel.recv_exit_status()
print('Done!')
ssh.close()
