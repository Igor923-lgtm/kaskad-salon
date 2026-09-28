import os as _os, sys as _sys
_sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..")))
import deploy_secrets
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password=deploy_secrets.PASS_HAIROS_OLD, timeout=15)

# Fix remaining kaskad reference on line 273
stdin, stdout, stderr = ssh.exec_command("sed -i 's|yandex.by/maps/org/kaskad/1176196517|yandex.by/maps/org/hairos/140988298647|g' /opt/hairos-bot/bot.py")
stdout.channel.recv_exit_status()
print("Replaced map URL")

# Also check for any other kaskad references
stdin, stdout, stderr = ssh.exec_command("grep -in kaskad /opt/hairos-bot/bot.py")
remaining = stdout.read().decode()
if remaining:
    print("Still has kaskad:", remaining)
else:
    print("No more kaskad references!")

# Also check other files
stdin, stdout, stderr = ssh.exec_command("grep -rn kaskad /opt/hairos-bot/bot.py /opt/hairos-bot/api.py /opt/hairos-bot/config.py /opt/hairos-bot/db.py 2>/dev/null")
all_refs = stdout.read().decode()
if all_refs:
    print("Other refs:", all_refs)

# Restart
stdin, stdout, stderr = ssh.exec_command('systemctl restart hairos-polling hairos-bot')
stdout.channel.recv_exit_status()
print("Services restarted")

ssh.close()
print("Done!")
