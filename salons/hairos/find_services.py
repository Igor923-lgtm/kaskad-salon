import os as _os, sys as _sys
_sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..")))
import deploy_secrets
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password=deploy_secrets.PASS_HAIROS_OLD, timeout=15)

# List all bot-related services
stdin, stdout, stderr = ssh.exec_command('systemctl list-units --type=service --all | grep -i "kaskad\|bot\|salon"')
print("Services:", stdout.read().decode())

# Check what's in /opt
stdin, stdout, stderr = ssh.exec_command('ls -la /opt/ 2>/dev/null')
print("/opt:", stdout.read().decode())

# Check what's running on port 8000
stdin, stdout, stderr = ssh.exec_command('curl -s -m 3 http://localhost:8000/health 2>&1')
print("Port 8000 health:", stdout.read().decode())

# Check what's running on port 8005
stdin, stdout, stderr = ssh.exec_command('curl -s -m 3 http://localhost:8005/health 2>&1')
print("Port 8005 health:", stdout.read().decode())

ssh.close()
