import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

# Read bot.py
stdin, stdout, stderr = ssh.exec_command("cat /opt/hairos-bot/bot.py")
content = stdout.read().decode('utf-8')

# Remove admin panel button from main menu
content = content.replace(
    '            [InlineKeyboardButton("\u2699\ufe0f \u0410\u0434\u043c\u0438\u043d-\u043f\u0430\u043d\u0435\u043b\u044c", callback_data="admin_menu")],\n',
    ''
)

# Replace any remaining КАСКАД with Hairos Studio
content = content.replace('\u041a\u0410\u0421\u041a\u0410\u0414', 'Hairos Studio')
content = content.replace('\u041a\u0430\u0441\u043a\u0430\u0434', 'Hairos Studio')
content = content.replace('KASKAD', 'Hairos Studio')

# Write back
sftp = ssh.open_sftp()
f = sftp.open('/opt/hairos-bot/bot.py', 'w')
f.write(content.encode('utf-8'))
f.close()
sftp.close()

print("bot.py updated: admin panel removed, КАСКАД replaced")

# Verify
stdin, stdout, stderr = ssh.exec_command("grep -c 'admin_menu' /opt/hairos-bot/bot.py")
print("admin_menu refs:", stdout.read().decode().strip())
stdin, stdout, stderr = ssh.exec_command("grep -ci 'kaskad\|КАСКАД' /opt/hairos-bot/bot.py")
print("KASKAD refs:", stdout.read().decode().strip())

# Restart
stdin, stdout, stderr = ssh.exec_command('systemctl restart hairos-polling')
stdout.channel.recv_exit_status()
print("Bot restarted")

ssh.close()
print("Done!")
