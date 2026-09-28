import os as _os, sys as _sys
_sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..")))
import deploy_secrets
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password=deploy_secrets.PASS_HAIROS_OLD, timeout=15)

# Check polling logs
stdin, stdout, stderr = ssh.exec_command('journalctl -u hairos-polling -n 40 --no-pager 2>&1')
logs = stdout.read().decode()
print(logs[-3000:])

ssh.close()
