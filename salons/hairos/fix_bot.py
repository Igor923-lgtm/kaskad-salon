import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

# Use sed to replace specific strings
replacements = [
    # Address
    ("52 (\u0446\u043e\u043a\u043e\u043b\u044c\u043d\u044b\u0439 \u044d\u0442\u0430\u0436)", "\u043f\u0440\u043e\u0441\u043f. \u0414\u0437\u0435\u0440\u0436\u0438\u043d\u0441\u043a\u043e\u0433\u043e, 15"),
    # Phone
    ("+375 29 120-61-01", "+375 29 504-08-79"),
    # Hours
    ("\u043f\u043d-\u043f\u0442 10:00\u201321:00; \u0441\u0431 11:00\u201320:00; \u0432\u0441 11:00\u201317:00", "\u0435\u0436\u0435\u0434\u043d\u0435\u0432\u043d\u043e 10:00\u201322:00"),
    # Map URL
    ("https://yandex.by/maps/org/kaskad/1176196517/?ll=27.512334%2C53.908495&z=14", "https://yandex.by/maps/org/hairos/140988298647/?ll=27.519399%2C53.887335&z=17.31"),
    # Phone in contact
    ("\u0422\u0435\u043b\u0435\u0444\u043e\u043d: +375 29 120-61-01", "\u0422\u0435\u043b\u0435\u0444\u043e\u043d: +375 29 504-08-79"),
    # Contact hours
    ("\u041f\u043d-\u0412\u0441: 10:00\u201321:00", "\u0415\u0436\u0435\u0434\u043d\u0435\u0432\u043d\u043e: 10:00\u201322:00"),
    # Call button
    ("tel:+375291206101", "tel:+375295040879"),
    # SALON_NAME
    ("\u041a\u0410\u0421\u041a\u0410\u0414", "Hairos Studio"),
]

for old, new in replacements:
    cmd = f"sed -i 's|{old}|{new}|g' /opt/hairos-bot/bot.py"
    stdin, stdout, stderr = ssh.exec_command(cmd)
    stdout.channel.recv_exit_status()
    err = stderr.read().decode()
    if err:
        print(f"Error replacing '{old[:30]}...': {err}")
    else:
        print(f"OK: '{old[:30]}...' -> '{new[:30]}...'")

# Verify
stdin, stdout, stderr = ssh.exec_command("grep -n '504-08-79' /opt/hairos-bot/bot.py")
print("Phone check:", stdout.read().decode())
stdin, stdout, stderr = ssh.exec_command("grep -n 'hairos' /opt/hairos-bot/bot.py")
print("Hairos check:", stdout.read().decode())

# Restart
stdin, stdout, stderr = ssh.exec_command('systemctl restart hairos-polling hairos-bot')
stdout.channel.recv_exit_status()
print("Services restarted")

ssh.close()
print("Done!")
