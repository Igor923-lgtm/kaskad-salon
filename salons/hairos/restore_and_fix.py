import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

# 1. Restore bot.py from KASKAD
ssh.exec_command('cp /opt/telegram-bot/bot.py /opt/hairos-bot/bot.py')
print("Restored bot.py from KASKAD")

# 2. Apply Hairos branding
stdin, stdout, stderr = ssh.exec_command("cat /opt/hairos-bot/bot.py")
content = stdout.read().decode('utf-8')

# Replace KASKAD data with Hairos
content = content.replace('Кальварийская ул., 52', 'просп. Дзержинского, 15')
content = content.replace('(цокольный этаж)', '(Между 10 по лестнице вниз, подъезд и 11)')
content = content.replace('Пн-Пт: 10:00 \u2013 21:00', 'Ежедневно: 10:00 \u2013 22:00')
content = content.replace('Сб: 11:00 \u2013 20:00', '')
content = content.replace('Вс: 11:00 \u2013 17:00', '')
content = content.replace('Молодёжная (680 м)', 'Грушевка (274 м)')
content = content.replace('+375 29 120-61-01', '+375 29 504-08-79')
content = content.replace('+375 (17) 350-81-91', '')
content = content.replace('tel:+375291206101', 'tel:+375295040879')
content = content.replace('kaskad/1176196517', 'hairos/140988298647')
content = content.replace('KASKAD', 'Hairos Studio')
content = content.replace('КАСКАД', 'Hairos Studio')

# 3. Remove ONLY the admin panel button from main menu (line 172 area)
# The button is added in cmd_start for admin users
content = content.replace(
    '        kb = InlineKeyboardMarkup(list(main_menu_kb().inline_keyboard) + [\n            [InlineKeyboardButton("\u2699\ufe0f \u0410\u0434\u043c\u0438\u043d-\u043f\u0430\u043d\u0435\u043b\u044c", callback_data="admin_menu")],\n        ])',
    '        kb = main_menu_kb()'
)

# Also remove from back_main handler
content = content.replace(
    '            kb = InlineKeyboardMarkup(list(main_menu_kb().inline_keyboard) + [\n                [InlineKeyboardButton("\u2699\ufe0f \u0410\u0434\u043c\u0438\u043d-\u043f\u0430\u043d\u0435\u043b\u044c", callback_data="admin_menu")],\n            ])',
    '            kb = main_menu_kb()'
)

# 4. Add logout confirmation
content = content.replace(
    'function logout() {\n  localStorage.removeItem(\'master_token\');\n  localStorage.removeItem(\'master_name\');\n  localStorage.removeItem(\'master_id\');\n  window.location.href = \'/master\';\n}',
    'function logout() {\n  if (confirm(\'Вы действительно хотите выйти?\')) {\n    localStorage.removeItem(\'master_token\');\n    localStorage.removeItem(\'master_name\');\n    localStorage.removeItem(\'master_id\');\n    window.location.href = \'/master\';\n  }\n}'
)

# Write back
sftp = ssh.open_sftp()
f = sftp.open('/opt/hairos-bot/bot.py', 'w')
f.write(content.encode('utf-8'))
f.close()
sftp.close()
print("Hairos branding applied, admin button removed, logout confirmation added")

# 5. Restart
stdin, stdout, stderr = ssh.exec_command('systemctl restart hairos-polling')
stdout.channel.recv_exit_status()
print("Bot restarted")

# 6. Verify
stdin, stdout, stderr = ssh.exec_command("grep -c 'admin_menu' /opt/hairos-bot/bot.py")
print(f"admin_menu refs: {stdout.read().decode().strip()} (should be >0 for handlers)")
stdin, stdout, stderr = ssh.exec_command("grep -c 'KASKAD\|КАСКАД' /opt/hairos-bot/bot.py")
print(f"KASKAD refs: {stdout.read().decode().strip()} (should be 0)")

ssh.close()
print("Done!")
