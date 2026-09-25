import paramiko, os, time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)
sftp = ssh.open_sftp()

templates_dir = r'C:\Users\User\mimo\kaskad-multitenant\templates'
remote_base = '/opt/hairos-bot/templates'

files = [
    '_sidebar.html',
    'schedule.html',
    'master_dashboard.html',
    'master_login.html',
    'clients_page.html',
    'crm_dashboard.html',
    'book.html',
    'bookings_page.html',
    'login.html',
    'widget.html',
    'client_analytics.html',
    'masters.html',
    'finance.html',
    'settings.html',
    'users_page.html',
]

for name in files:
    local = os.path.join(templates_dir, name)
    remote = f'{remote_base}/{name}'
    if os.path.exists(local):
        sftp.put(local, remote)
        print(f'OK: {name}')
    else:
        print(f'SKIP: {name} not found')

sftp.close()

stdin, stdout, stderr = ssh.exec_command('systemctl restart hairos-bot hairos-polling')
stdout.channel.recv_exit_status()
print('Services restarted')

time.sleep(3)
stdin, stdout, stderr = ssh.exec_command('curl -s http://localhost:8005/health')
print(f'Health: {stdout.read().decode().strip()}')

stdin, stdout, stderr = ssh.exec_command('systemctl is-active hairos-bot hairos-polling')
print(f'Services: {stdout.read().decode().strip()}')

ssh.close()
print('Deploy complete!')
