import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

# Check logs from ~7 hours ago (07:00-09:00 UTC on Sep 2)
stdin, stdout, stderr = ssh.exec_command('journalctl -u hairos-polling --since "2026-09-02 07:00" --until "2026-09-02 09:00" --no-pager 2>&1')
logs = stdout.read().decode()

print("=== LOGS 07:00-09:00 UTC ===")
lines = logs.strip().split('\n')
for line in lines:
    if line.strip():
        print(line)

# Check for restarts/errors in wider window
stdin, stdout, stderr = ssh.exec_command('journalctl -u hairos-polling --since "2026-09-02 05:00" --until "2026-09-02 12:00" --no-pager 2>&1 | grep -i "error\\|exception\\|traceback\\|restart\\|stop\\|start\\|fail"')
err_lines = stdout.read().decode()
print("\n=== ERRORS/RESTARTS ===")
for line in err_lines.strip().split('\n'):
    if line.strip():
        print(line)

# Check current bot status
stdin, stdout, stderr = ssh.exec_command('systemctl status hairos-polling --no-pager | head -15')
print("\n=== CURRENT STATUS ===")
print(stdout.read().decode())

ssh.close()
