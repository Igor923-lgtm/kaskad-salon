import os as _os, sys as _sys
_sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..")))
import deploy_secrets
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password=deploy_secrets.PASS_HAIROS_OLD, timeout=15)

# Login to Hairos
stdin, stdout, stderr = ssh.exec_command(f'curl -s -c /tmp/h_cookies.txt -L -d "password={os.environ["QA_HAIROS_PW"]}" http://localhost:8005/login -o /dev/null')

# Test broadcast with client_ids
stdin, stdout, stderr = ssh.exec_command('curl -s -b /tmp/h_cookies.txt -X POST http://localhost:8005/api/broadcast -H "Content-Type: application/json" -d \'{"client_ids":[294308582],"text":"Тест рассылки по выбору"}\'')
print(f"Hairos broadcast: {stdout.read().decode().strip()}")

# Login to Kaskad
stdin, stdout, stderr = ssh.exec_command(f'curl -s -c /tmp/k_cookies.txt -L -d "password={os.environ["QA_KASKAD_PW"]}" http://localhost:8000/login -o /dev/null')

# Test broadcast with client_ids
stdin, stdout, stderr = ssh.exec_command('curl -s -b /tmp/k_cookies.txt -X POST http://localhost:8000/api/broadcast -H "Content-Type: application/json" -d \'{"client_ids":[294308582],"text":"Тест рассылки по выбору"}\'')
print(f"Kaskad broadcast: {stdout.read().decode().strip()}")

ssh.close()
