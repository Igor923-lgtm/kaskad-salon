import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

# Replace KASKAD with Hairos Studio in all templates and static files
for pattern in ['/opt/hairos-bot/templates/*.html', '/opt/hairos-bot/static/manifest.json', '/opt/hairos-bot/static/style.css']:
    ssh.exec_command(f"sed -i 's/KASKAD CRM/Hairos Studio CRM/g' {pattern}")
    ssh.exec_command(f"sed -i 's/KASKAD/Hairos Studio/g' {pattern}")

print("Templates rebranded")

# Fix bot.py location data
stdin, stdout, stderr = ssh.exec_command("cat /opt/hairos-bot/bot.py")
content = stdout.read().decode('utf-8')

content = content.replace('Кальварийская ул., 52', 'просп. Дзержинского, 15')
content = content.replace('(цокольный этаж)', '(Между 10 по лестнице вниз, подъезд и 11)')
content = content.replace('Пн-Пт: 10:00 \u2013 21:00', 'Ежедневно: 10:00 \u2013 22:00')
content = content.replace('Сб: 11:00 \u2013 20:00', '')
content = content.replace('Вс: 11:00 \u2013 17:00', '')
content = content.replace('Молодёжная (680 м)', 'Грушевка (274 м)')
content = content.replace('+375 29 120-61-01', '+375 29 504-08-79')
content = content.replace('+375 (17) 350-81-91', '')
content = content.replace('tel:+375291206101', 'tel:+375295040879')
content = content.replace('kaskad/1176196517', 'hairos/140988298647')

sftp = ssh.open_sftp()
f = sftp.open('/opt/hairos-bot/bot.py', 'w')
f.write(content.encode('utf-8'))
f.close()
sftp.close()

print("bot.py location data fixed")

# Add finance to public paths
stdin, stdout, stderr = ssh.exec_command("cat /opt/hairos-bot/api.py")
api_content = stdout.read().decode('utf-8')
api_content = api_content.replace(
    'PUBLIC_PATHS = {"/health", "/login", "/api/slots", "/api/services", "/api/masters", "/api/salon-hours", "/widget", "/book", "/static"}',
    'PUBLIC_PATHS = {"/health", "/login", "/api/slots", "/api/services", "/api/masters", "/api/salon-hours", "/api/finance/summary", "/api/transactions", "/widget", "/book", "/static"}'
)
api_content = api_content.replace('crm_token', 'hairos_token')

sftp = ssh.open_sftp()
f = sftp.open('/opt/hairos-bot/api.py', 'w')
f.write(api_content.encode('utf-8'))
f.close()
sftp.close()

print("api.py fixed (public paths + cookie)")

# Restart
stdin, stdout, stderr = ssh.exec_command('systemctl restart hairos-bot hairos-polling')
stdout.channel.recv_exit_status()
print("Services restarted")

ssh.close()
print("Done!")
