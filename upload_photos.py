"""upload_photos.py — Загрузка фото работ на оба сервера."""
import paramiko
import os

SERVER = "92.246.128.94"
USER = "root"
PASS = "kf24mP2c7KQBViNi"
LOCAL_PROJECT = r"C:\Users\User\mimo\kaskad-multitenant"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(SERVER, username=USER, password=PASS, timeout=15)
print("Connected\n")

sftp = ssh.open_sftp()

# Upload works_photos to both services
works_dir = os.path.join(LOCAL_PROJECT, "works_photos")

for svc in ["kaskad", "hairos"]:
    print(f"=== {svc.upper()} ===")

    # Create remote works_photos directory
    ssh.exec_command(f"mkdir -p /opt/{svc}-bot/works_photos")

    # Upload root-level photos
    for f in os.listdir(works_dir):
        local_path = os.path.join(works_dir, f)
        if os.path.isfile(local_path) and f.lower().endswith(('.jpg', '.png', '.jpeg')):
            remote_path = f"/opt/{svc}-bot/works_photos/{f}"
            sftp.put(local_path, remote_path)
            print(f"  {f} ({os.path.getsize(local_path) // 1024}KB)")

    # Upload subdirectory photos
    for subdir in os.listdir(works_dir):
        subdir_path = os.path.join(works_dir, subdir)
        if os.path.isdir(subdir_path):
            remote_subdir = f"/opt/{svc}-bot/works_photos/{subdir}"
            ssh.exec_command(f"mkdir -p {remote_subdir}")
            for f in os.listdir(subdir_path):
                local_path = os.path.join(subdir_path, f)
                if os.path.isfile(local_path) and f.lower().endswith(('.jpg', '.png', '.jpeg')):
                    remote_path = f"{remote_subdir}/{f}"
                    sftp.put(local_path, remote_path)
                    print(f"  {subdir}/{f} ({os.path.getsize(local_path) // 1024}KB)")

    # Upload salon_logo.png if exists
    local_salon_logo = os.path.join(LOCAL_PROJECT, "salons", "hairos", "icon-192.png")
    # Actually upload the main logo
    local_logo = os.path.join(LOCAL_PROJECT, "logo.png")
    if os.path.exists(local_logo):
        sftp.put(local_logo, f"/opt/{svc}-bot/static/logo.png")
        print(f"  static/logo.png")

    print()

sftp.close()
ssh.close()
print("=== ГОТОВО ===")
