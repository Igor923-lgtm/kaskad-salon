import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

# Check master login page
stdin, stdout, stderr = ssh.exec_command('curl -s -o /dev/null -w "%{http_code}" http://localhost:8005/master')
print(f"Master login page: HTTP {stdout.read().decode().strip()}")

# Check master dashboard page
stdin, stdout, stderr = ssh.exec_command('curl -s -o /dev/null -w "%{http_code}" http://localhost:8005/master/dashboard')
print(f"Master dashboard page: HTTP {stdout.read().decode().strip()}")

# Check CRM login page
stdin, stdout, stderr = ssh.exec_command('curl -s -o /dev/null -w "%{http_code}" http://localhost:8005/login')
print(f"CRM login page: HTTP {stdout.read().decode().strip()}")

# Check CRM dashboard (should redirect without cookie)
stdin, stdout, stderr = ssh.exec_command('curl -s -o /dev/null -w "%{http_code}" http://localhost:8005/dashboard')
print(f"CRM dashboard (no auth): HTTP {stdout.read().decode().strip()}")

# Check bot polling service
stdin, stdout, stderr = ssh.exec_command('systemctl is-active hairos-polling')
print(f"Bot polling: {stdout.read().decode().strip()}")

# Check recent bot logs
stdin, stdout, stderr = ssh.exec_command('journalctl -u hairos-polling --since 5min --no-pager | tail -5')
print(f"\nBot logs (last 5min):\n{stdout.read().decode()}")

ssh.close()
