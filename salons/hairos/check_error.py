import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

# Get full error logs
stdin, stdout, stderr = ssh.exec_command('journalctl -u hairos-bot --since 5min --no-pager -p err')
print("=== Error logs ===")
print(stdout.read().decode())

# Also try running manually to see the error
stdin, stdout, stderr = ssh.exec_command('cd /opt/hairos-bot && source venv/bin/activate && python -c "import api" 2>&1')
print("=== Import test ===")
print(stdout.read().decode()[:2000])
print(stderr.read().decode()[:2000])

ssh.close()
