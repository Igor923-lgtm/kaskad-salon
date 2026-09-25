import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

# Read master_dashboard.html
stdin, stdout, stderr = ssh.exec_command("cat /opt/hairos-bot/templates/master_dashboard.html")
content = stdout.read().decode('utf-8')

# Replace simple logout with confirmation dialog
old_logout = """function logout() {
  localStorage.removeItem('master_token');
  localStorage.removeItem('master_name');
  localStorage.removeItem('master_id');
  window.location.href = '/master';
}"""

new_logout = """function logout() {
  if (confirm('Вы действительно хотите выйти?')) {
    localStorage.removeItem('master_token');
    localStorage.removeItem('master_name');
    localStorage.removeItem('master_id');
    window.location.href = '/master';
  }
}"""

content = content.replace(old_logout, new_logout)

# Write back
sftp = ssh.open_sftp()
f = sftp.open('/opt/hairos-bot/templates/master_dashboard.html', 'w')
f.write(content.encode('utf-8'))
f.close()
sftp.close()
print("Logout confirmation added")

# Restart CRM
stdin, stdout, stderr = ssh.exec_command('systemctl restart hairos-bot')
stdout.channel.recv_exit_status()
print("CRM restarted")

ssh.close()
print("Done!")
