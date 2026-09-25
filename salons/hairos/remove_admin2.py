import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

# Remove admin panel button lines
stdin, stdout, stderr = ssh.exec_command("sed -i '/admin_menu/d' /opt/hairos-bot/bot.py")
stdout.channel.recv_exit_status()
print("Removed all admin_menu references")

# Verify
stdin, stdout, stderr = ssh.exec_command("grep -c admin_menu /opt/hairos-bot/bot.py")
count = stdout.read().decode().strip()
print(f"admin_menu refs remaining: {count}")

# Restart
stdin, stdout, stderr = ssh.exec_command('systemctl restart hairos-polling')
stdout.channel.recv_exit_status()
print("Bot restarted")

ssh.close()
print("Done!")
