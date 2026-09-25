import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('92.246.128.94', username='root', password='kf24mP2c7KQBViNi', timeout=15)

manifest = """{
  "name": "Hairos Studio CRM",
  "short_name": "Hairos",
  "description": "CRM для салона Hairos Studio",
  "start_url": "/master/dashboard",
  "display": "standalone",
  "background_color": "#ffffff",
  "theme_color": "#6366f1",
  "orientation": "portrait",
  "icons": [
    {"src": "/static/icon-192.png?v=3", "sizes": "192x192", "type": "image/png"},
    {"src": "/static/icon-512.png?v=3", "sizes": "512x512", "type": "image/png"}
  ]
}"""

sftp = ssh.open_sftp()
f = sftp.open('/opt/hairos-bot/static/manifest.json', 'w')
f.write(manifest)
f.close()
sftp.close()

print("OK: manifest обновлён (v3)")
ssh.close()
