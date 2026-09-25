import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

# Check if Kaskad bot has edit booking
stdin, stdout, stderr = ssh.exec_command('grep -c "menu_edit_booking" /opt/telegram-bot/bot.py')
print(f"Edit booking in Kaskad bot: {stdout.read().decode().strip()} occurrences")

# Check broadcast endpoint
stdin, stdout, stderr = ssh.exec_command('curl -s -c /tmp/kaskad_cookies.txt -L -d "password=kaskad2026" http://localhost:8000/login -o /dev/null')
stdout.read()

stdin, stdout, stderr = ssh.exec_command('curl -s -b /tmp/kaskad_cookies.txt -X POST http://localhost:8000/api/broadcast -H "Content-Type: application/json" -d \'{"segment":"all","text":"test"}\'')
print(f"Broadcast: {stdout.read().decode().strip()}")

# Check bot logs
stdin, stdout, stderr = ssh.exec_command('journalctl -u telegram-bot --since 1min --no-pager | tail -3')
print(f"\nBot logs:\n{stdout.read().decode()}")

ssh.close()
