import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

print("=== HAIROS PROJECT HEALTH CHECK ===\n")

# 1. Services status
stdin, stdout, stderr = ssh.exec_command("systemctl is-active hairos-bot hairos-polling")
print("Services:", stdout.read().decode().strip())

# 2. Health endpoint
stdin, stdout, stderr = ssh.exec_command("curl -s http://localhost:8005/health")
print("Health:", stdout.read().decode().strip())

# 3. Masters API
stdin, stdout, stderr = ssh.exec_command("curl -s http://localhost:8005/api/masters")
print("Masters API:", "OK" if "Кристина" in stdout.read().decode() else "ERROR")

# 4. Services API
stdin, stdout, stderr = ssh.exec_command("curl -s http://localhost:8005/api/services")
print("Services API:", "OK" if "Наращивание" in stdout.read().decode() else "ERROR")

# 5. Salon hours
stdin, stdout, stderr = ssh.exec_command("curl -s http://localhost:8005/api/salon-hours")
print("Salon Hours:", stdout.read().decode().strip()[:100])

# 6. Login page
stdin, stdout, stderr = ssh.exec_command("curl -s http://localhost:8005/login")
print("Login Page:", "OK" if "Hairos" in stdout.read().decode() else "ERROR")

# 7. Master app
stdin, stdout, stderr = ssh.exec_command("curl -s http://localhost:8005/master")
print("Master App:", "OK" if "master" in stdout.read().decode().lower() else "ERROR")

# 8. Masters-with-bookings
stdin, stdout, stderr = ssh.exec_command("curl -s http://localhost:8005/api/masters-with-bookings")
print("Masters+Bookings:", "OK" if "Кристина" in stdout.read().decode() else "ERROR")

# 9. Bot logs (last 5 lines)
stdin, stdout, stderr = ssh.exec_command("journalctl -u hairos-polling --since 5min --no-pager | tail -5")
print("\nBot logs (last 5min):")
print(stdout.read().decode())

# 10. CRM logs (last 5 lines)
stdin, stdout, stderr = ssh.exec_command("journalctl -u hairos-bot --since 5min --no-pager | tail -5")
print("CRM logs (last 5min):")
print(stdout.read().decode())

ssh.close()
print("=== CHECK COMPLETE ===")
