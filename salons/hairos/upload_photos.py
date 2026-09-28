import os as _os, sys as _sys
_sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..")))
import deploy_secrets
import paramiko
from PIL import Image
import pillow_heif
import os

# Convert HEIC to JPG and upload
desktop = r'C:\Users\User\Desktop\Хайрос'
photos = [f for f in os.listdir(desktop) if f.endswith('.HEIC')]

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password=deploy_secrets.PASS_HAIROS_OLD, timeout=15)
sftp = ssh.open_sftp()

for photo in photos:
    heic_path = os.path.join(desktop, photo)
    jpg_name = photo.replace('.HEIC', '.jpg')
    jpg_path = os.path.join(desktop, jpg_name)
    
    # Convert HEIC to JPG
    heif_file = pillow_heif.read_heif(heic_path)
    img = Image.frombytes(heif_file.mode, heif_file.size, heif_file.data)
    img.save(jpg_path, 'JPEG', quality=85)
    print(f'Converted: {photo} -> {jpg_name}')
    
    # Upload
    sftp.put(jpg_path, f'/opt/hairos-bot/works_photos/{jpg_name}')
    print(f'  Uploaded to server')
    
    # Clean up local JPG
    os.remove(jpg_path)

sftp.close()
ssh.close()
print('All photos converted and uploaded!')
