import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

# Read file
stdin, stdout, stderr = ssh.exec_command("cat /opt/hairos-bot/bot.py")
content = stdout.read().decode('utf-8')

# Simple replacements
content = content.replace('Кальварийская ул., 52', 'просп. Дзержинского, 15')
content = content.replace('(цокольный этаж)', '(Между 10 по лестнице вниз, подъезд и 11)')
content = content.replace('Пн-Пт: 10:00 \u2013 21:00', 'Ежедневно: 10:00 \u2013 22:00')
content = content.replace('Сб: 11:00 \u2013 20:00', '')
content = content.replace('Вс: 11:00 \u2013 17:00', '')

# Write back
sftp = ssh.open_sftp()
f = sftp.open('/opt/hairos-bot/bot.py', 'w')
f.write(content.encode('utf-8'))
f.close()
sftp.close()

print("File updated")

# Verify
stdin, stdout, stderr = ssh.exec_command("sed -n 266,280p /opt/hairos-bot/bot.py")
print("Location function:")
print(stdout.read().decode())

# Restart
stdin, stdout, stderr = ssh.exec_command('systemctl restart hairos-polling')
stdout.channel.recv_exit_status()
print("Bot restarted")

ssh.close()
print("Done!")
