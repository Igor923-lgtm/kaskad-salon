import os as _os, sys as _sys
_sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..")))
import deploy_secrets
import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password=deploy_secrets.PASS_HAIROS_OLD, timeout=15)

# Find where kaskad-multitenant is on the server
stdin, stdout, stderr = ssh.exec_command('find / -name "docker-compose.yml" -path "*/kaskad*" 2>/dev/null | head -5')
print("Docker compose files:", stdout.read().decode())

# Check if docker is available
stdin, stdout, stderr = ssh.exec_command('docker --version 2>&1 && docker-compose --version 2>&1')
print("Docker:", stdout.read().decode())

# Check running containers
stdin, stdout, stderr = ssh.exec_command('docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>&1')
print("Containers:", stdout.read().decode())

ssh.close()
