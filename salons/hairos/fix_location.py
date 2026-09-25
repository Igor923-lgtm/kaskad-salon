import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

# Fix cb_location function - replace all hardcoded KASKAD values
replacements = [
    # Address in location function
    ("Кальварийская ул., 52\n(цокольный этаж)", "просп. Дзержинского, 15\n(Между 10 по лестнице вниз, подъезд и 11)"),
    # Secondary phone
    ("+375 (17) 350-81-91", ""),
    # Working hours
    ("Пн-Пт: 10:00 – 21:00\\nСб: 11:00 – 20:00\\nВс: 11:00 – 17:00", "Ежедневно: 10:00 – 22:00"),
    # Metro
    ("Молодёжная (680 м)", "Грушевка (274 м)"),
    # Also fix SALON_ADDRESS line 234
    ("Кальварийская ул., просп. Дзержинского, 15", "просп. Дзержинского, 15"),
]

for old, new in replacements:
    cmd = f"sed -i 's|{old}|{new}|g' /opt/hairos-bot/bot.py"
    stdin, stdout, stderr = ssh.exec_command(cmd)
    stdout.channel.recv_exit_status()
    err = stderr.read().decode()
    if err:
        print(f"Error: {err[:100]}")
    else:
        print(f"OK: replaced")

# Verify
stdin, stdout, stderr = ssh.exec_command("sed -n 234,237p /opt/hairos-bot/bot.py")
print("\nLines 234-237:")
print(stdout.read().decode())

stdin, stdout, stderr = ssh.exec_command("sed -n 266,280p /opt/hairos-bot/bot.py")
print("Lines 266-280 (location):")
print(stdout.read().decode())

# Restart
stdin, stdout, stderr = ssh.exec_command('systemctl restart hairos-polling')
stdout.channel.recv_exit_status()
print("Bot restarted")

ssh.close()
print("Done!")
