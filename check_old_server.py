import paramiko

OLD_SERVER = '94.141.98.224'
USER = 'root'
PASS = '25ELkJTNxhwCC7vF'

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(OLD_SERVER, username=USER, password=PASS, timeout=15)
print(f"Connected to {OLD_SERVER}\n")

checks = [
    ("Docker version", "docker --version"),
    ("Docker Compose", "docker-compose --version || docker compose version"),
    ("Running containers", "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"),
    ("All containers", "docker ps -a --format 'table {{.Names}}\t{{.Status}}'"),
    ("Project files /opt", "ls -la /opt/"),
    ("Hairos files", "ls -la /opt/hairos-bot/ 2>/dev/null | head -15"),
    ("Kaskad files", "ls -la /opt/kaskad-bot/ 2>/dev/null | head -15"),
    ("Systemd services", "systemctl list-units --type=service --state=running | grep -E 'bot|hairos|kaskad|salon'"),
    ("Nginx config", "ls /etc/nginx/conf.d/ 2>/dev/null"),
    ("Ports listening", "ss -tlnp | grep -E '800[0-5]|80|443'"),
]

for name, cmd in checks:
    try:
        stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()
        result = out if out else (err if err else "(empty)")
        print(f"--- {name} ---")
        for line in result.split('\n')[:15]:
            print(f"  {line}")
        print()
    except Exception as e:
        print(f"--- {name} --- ERROR: {e}\n")

ssh.close()
