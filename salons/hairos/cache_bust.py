import paramiko
import time

ts = int(time.time())

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

# Add cache-busting to master_dashboard.html
stdin, stdout, stderr = ssh.exec_command(
    f"sed -i 's|icon-192.png|icon-192.png?v={ts}|g; s|icon-512.png|icon-512.png?v={ts}|g; s|manifest.json|manifest.json?v={ts}|g' /opt/hairos-bot/templates/master_dashboard.html"
)
stdout.channel.recv_exit_status()
print(f"Cache-busted master_dashboard.html with v={ts}")

# Also add to master_login.html
stdin, stdout, stderr = ssh.exec_command(
    f"sed -i 's|icon-192.png|icon-192.png?v={ts}|g; s|manifest.json|manifest.json?v={ts}|g' /opt/hairos-bot/templates/master_login.html"
)
stdout.channel.recv_exit_status()
print("Cache-busted master_login.html")

# Restart
stdin, stdout, stderr = ssh.exec_command('systemctl restart hairos-bot')
stdout.channel.recv_exit_status()
print("CRM restarted")

ssh.close()
print("Done!")
