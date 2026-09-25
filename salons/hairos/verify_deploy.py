import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

time.sleep(3)

# Health check
stdin, stdout, stderr = ssh.exec_command('curl -s http://localhost:8005/health')
print(f"Health: {stdout.read().decode().strip()}")

# Test bookings grouped
stdin, stdout, stderr = ssh.exec_command('curl -s http://localhost:8005/api/bookings/grouped | head -c 300')
print(f"Bookings grouped: {stdout.read().decode().strip()}")

# Test broadcast endpoint exists
stdin, stdout, stderr = ssh.exec_command('curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8005/api/broadcast -H "Content-Type: application/json" -d \'{"segment":"all","text":"test"}\'')
print(f"Broadcast: HTTP {stdout.read().decode().strip()}")

# Check services
stdin, stdout, stderr = ssh.exec_command('systemctl is-active hairos-bot hairos-polling')
print(f"Services: {stdout.read().decode().strip()}")

# Check bot logs for edit booking
stdin, stdout, stderr = ssh.exec_command('journalctl -u hairos-polling --since 10min --no-pager | tail -5')
print(f"\nBot logs:\n{stdout.read().decode()}")

ssh.close()
