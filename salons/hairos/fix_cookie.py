import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

stdin, stdout, stderr = ssh.exec_command("sed -i 's/crm_token/hairos_token/g' /opt/hairos-bot/api.py")
stdout.channel.recv_exit_status()
print("Cookie renamed to hairos_token")

stdin, stdout, stderr = ssh.exec_command("grep -n hairos_token /opt/hairos-bot/api.py")
print(stdout.read().decode())

stdin, stdout, stderr = ssh.exec_command('systemctl restart hairos-bot')
stdout.channel.recv_exit_status()
print("CRM restarted")

ssh.close()
print("Done!")
