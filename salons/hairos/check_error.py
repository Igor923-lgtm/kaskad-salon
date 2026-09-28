import os as _os, sys as _sys
_sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..")))
import deploy_secrets
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password=deploy_secrets.PASS_HAIROS_OLD, timeout=15)

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
