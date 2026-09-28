import os as _os, sys as _sys
_sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..")))
import deploy_secrets
import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password=deploy_secrets.PASS_HAIROS_OLD, timeout=15)

time.sleep(5)

# Get error logs
stdin, stdout, stderr = ssh.exec_command('journalctl -u hairos-bot --since 1min --no-pager')
print(stdout.read().decode())

# Try import test
stdin, stdout, stderr = ssh.exec_command('cd /opt/hairos-bot && source venv/bin/activate && python -c "import api; print(\'OK\')" 2>&1')
print("Import test:")
print(stdout.read().decode()[:1000])
print(stderr.read().decode()[:1000])

ssh.close()
