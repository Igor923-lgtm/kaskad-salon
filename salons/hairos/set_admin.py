import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

# Update .env
stdin, stdout, stderr = ssh.exec_command("sed -i 's/ADMIN_IDS=/ADMIN_IDS=294308582/' /opt/hairos-bot/salons/hairos/.env")
stdout.channel.recv_exit_status()
print("ADMIN_IDS updated in .env")

# Verify
stdin, stdout, stderr = ssh.exec_command("grep ADMIN_IDS /opt/hairos-bot/salons/hairos/.env")
print(stdout.read().decode())

# Restart services
stdin, stdout, stderr = ssh.exec_command("systemctl restart hairos-bot hairos-polling")
stdout.channel.recv_exit_status()
print("Services restarted")

ssh.close()
print("Done!")
