import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

tests = [
    ("Finance endpoint", "curl -s -o /dev/null -w '%{http_code}' http://localhost:8005/api/finance/summary"),
    ("Finance response", "curl -s http://localhost:8005/api/finance/summary"),
    ("Masters-with-bookings", "curl -s -o /dev/null -w '%{http_code}' http://localhost:8005/api/masters-with-bookings"),
    ("Bookings", "curl -s -o /dev/null -w '%{http_code}' http://localhost:8005/api/bookings"),
    ("Clients search", "curl -s -o /dev/null -w '%{http_code}' http://localhost:8005/api/clients/search/test"),
    ("Transactions", "curl -s -o /dev/null -w '%{http_code}' http://localhost:8005/api/transactions"),
]

for name, cmd in tests:
    stdin, stdout, stderr = ssh.exec_command(cmd)
    result = stdout.read().decode().strip()
    print(f"{name}: {result[:200]}")

ssh.close()
