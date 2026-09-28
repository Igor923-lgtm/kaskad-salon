import os as _os, sys as _sys
_sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..")))
import deploy_secrets
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password=deploy_secrets.PASS_HAIROS_OLD, timeout=15)

# Login to get cookie
stdin, stdout, stderr = ssh.exec_command(f'curl -s -c /tmp/cookies.txt -L -d "password={os.environ["QA_HAIROS_PW"]}" http://localhost:8005/login -o /dev/null -w "%{{http_code}}"')
print(f"Login: HTTP {stdout.read().decode().strip()}")

# Test bookings grouped with cookie
stdin, stdout, stderr = ssh.exec_command('curl -s -b /tmp/cookies.txt http://localhost:8005/api/bookings/grouped | head -c 500')
print(f"Grouped: {stdout.read().decode().strip()}")

# Test broadcast endpoint
stdin, stdout, stderr = ssh.exec_command('curl -s -b /tmp/cookies.txt -X POST http://localhost:8005/api/broadcast -H "Content-Type: application/json" -d \'{"segment":"all","text":"test"}\'')
print(f"Broadcast: {stdout.read().decode().strip()}")

# Test clients page
stdin, stdout, stderr = ssh.exec_command('curl -s -b /tmp/cookies.txt -o /dev/null -w "%{http_code}" http://localhost:8005/clients')
print(f"Clients page: HTTP {stdout.read().decode().strip()}")

# Test dashboard
stdin, stdout, stderr = ssh.exec_command('curl -s -b /tmp/cookies.txt -o /dev/null -w "%{http_code}" http://localhost:8005/dashboard')
print(f"Dashboard: HTTP {stdout.read().decode().strip()}")

# Check bot has edit booking
stdin, stdout, stderr = ssh.exec_command('grep -c "menu_edit_booking" /opt/hairos-bot/bot.py')
print(f"Edit booking in bot: {stdout.read().decode().strip()} occurrences")

ssh.close()
