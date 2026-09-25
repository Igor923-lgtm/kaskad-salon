import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

# Read api.py
stdin, stdout, stderr = ssh.exec_command("cat /opt/hairos-bot/api.py")
content = stdout.read().decode('utf-8')

# Add finance and transactions to public paths
old_paths = 'PUBLIC_PATHS = {"/health", "/login", "/api/slots", "/api/services", "/api/masters", "/api/salon-hours", "/widget", "/book", "/static"}'
new_paths = 'PUBLIC_PATHS = {"/health", "/login", "/api/slots", "/api/services", "/api/masters", "/api/salon-hours", "/api/finance/summary", "/api/transactions", "/widget", "/book", "/static"}'

content = content.replace(old_paths, new_paths)

# Write back
sftp = ssh.open_sftp()
f = sftp.open('/opt/hairos-bot/api.py', 'w')
f.write(content.encode('utf-8'))
f.close()
sftp.close()

print("Finance API added to public paths")

# Restart
stdin, stdout, stderr = ssh.exec_command("systemctl restart hairos-bot")
stdout.channel.recv_exit_status()
print("CRM restarted")

ssh.close()
print("Done!")
