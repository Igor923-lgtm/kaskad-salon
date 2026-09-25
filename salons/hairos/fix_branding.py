import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

# Replace KASKAD with Hairos Studio in all templates and static files
files = [
    '/opt/hairos-bot/templates/*.html',
    '/opt/hairos-bot/static/manifest.json',
    '/opt/hairos-bot/static/style.css',
]

for pattern in files:
    stdin, stdout, stderr = ssh.exec_command(f"sed -i 's/KASKAD CRM/Hairos Studio CRM/g' {pattern}")
    stdout.channel.recv_exit_status()
    stdin, stdout, stderr = ssh.exec_command(f"sed -i 's/KASKAD/Hairos Studio/g' {pattern}")
    stdout.channel.recv_exit_status()
    stdin, stdout, stderr = ssh.exec_command(f"sed -i 's/salon KASKAD/salon Hairos Studio/g' {pattern}")
    stdout.channel.recv_exit_status()

print("All KASKAD references replaced with Hairos Studio")

# Verify
stdin, stdout, stderr = ssh.exec_command("grep -rn KASKAD /opt/hairos-bot/templates/ /opt/hairos-bot/static/ 2>/dev/null")
remaining = stdout.read().decode()
if remaining:
    print("Still has KASKAD:", remaining)
else:
    print("No more KASKAD references!")

# Restart
stdin, stdout, stderr = ssh.exec_command('systemctl restart hairos-bot')
stdout.channel.recv_exit_status()
print("CRM restarted")

ssh.close()
print("Done!")
