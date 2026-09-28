import os as _os, sys as _sys
_sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..")))
import deploy_secrets
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password=deploy_secrets.PASS_HAIROS_OLD, timeout=15)

# Update .env
stdin, stdout, stderr = ssh.exec_command("sed -i 's/ADMIN_IDS=/ADMIN_IDS=294308582/' /opt/hairos-bot/salons/hairos/.env")
stdout.channel.recv_exit_status()
print("ADMIN_IDS updated in .env")

# Verify
stdin, stdout, stderr = ssh.exec_command("grep ADMIN_IDS /opt/hairos-bot/salons/hairos/.env")
print(stdout.read().decode())

# Restart services
stdin, stdout, stderr = ssh.exec_command("systemctl restart hairos-bot hairos-polling")
stdout.channel.recv_exit_status()
print("Services restarted")

ssh.close()
print("Done!")
