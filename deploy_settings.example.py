"""Деплой обновлений CRM — скопируйте в deploy_settings.py и заполните.
deploy_settings.py в .gitignore (содержит пароль)."""
import paramiko
import time

SERVER = "92.246.128.94"
USER = "root"
PASS = ""  # SSH password — only in deploy_settings.py, never commit
LOCAL = r"/Users/igor/mimo/kaskad-multitenant"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(SERVER, username=USER, password=PASS, timeout=15)
print("Connected\n")

sftp = ssh.open_sftp()

for svc in ["kaskad", "hairos"]:
    print(f"=== {svc} ===")
    sftp.put(f"{LOCAL}/api.py", f"/opt/{svc}-bot/api.py")
    print("  api.py")

sftp.close()

print("\n=== Restart ===")
ssh.exec_command("systemctl restart kaskad-crm kaskad-polling")
ssh.exec_command("systemctl restart hairos-crm hairos-polling")
time.sleep(5)

for svc in ["kaskad", "hairos"]:
    status = ssh.exec_command(f"systemctl is-active {svc}-crm {svc}-polling")[1].read().decode().strip()
    print(f"  {svc}: {status}")

print("\n=== Test ===")
for svc, port in [("kaskad", 8000), ("hairos", 8005)]:
    code = ssh.exec_command(
        f"curl -s -o /dev/null -w %{{http_code}} http://localhost:{port}/health --connect-timeout 5"
    )[1].read().decode()
    print(f"  {svc} /health: HTTP {code}")

ssh.close()
print("\n=== DONE ===")
