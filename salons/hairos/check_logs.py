import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

# Check polling logs
stdin, stdout, stderr = ssh.exec_command('journalctl -u hairos-polling -n 40 --no-pager 2>&1')
logs = stdout.read().decode()
print(logs[-3000:])

ssh.close()
