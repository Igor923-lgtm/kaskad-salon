import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

# Login to Hairos
stdin, stdout, stderr = ssh.exec_command('curl -s -c /tmp/h_cookies.txt -L -d "password=hairos2026" http://localhost:8005/login -o /dev/null')

# Test broadcast with client_ids
stdin, stdout, stderr = ssh.exec_command('curl -s -b /tmp/h_cookies.txt -X POST http://localhost:8005/api/broadcast -H "Content-Type: application/json" -d \'{"client_ids":[294308582],"text":"Тест рассылки по выбору"}\'')
print(f"Hairos broadcast: {stdout.read().decode().strip()}")

# Login to Kaskad
stdin, stdout, stderr = ssh.exec_command('curl -s -c /tmp/k_cookies.txt -L -d "password=kaskad2026" http://localhost:8000/login -o /dev/null')

# Test broadcast with client_ids
stdin, stdout, stderr = ssh.exec_command('curl -s -b /tmp/k_cookies.txt -X POST http://localhost:8000/api/broadcast -H "Content-Type: application/json" -d \'{"client_ids":[294308582],"text":"Тест рассылки по выбору"}\'')
print(f"Kaskad broadcast: {stdout.read().decode().strip()}")

ssh.close()
