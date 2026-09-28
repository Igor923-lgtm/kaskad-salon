import os as _os, sys as _sys
_sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..")))
import deploy_secrets
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password=deploy_secrets.PASS_HAIROS_OLD, timeout=15)

# Read bot.py
stdin, stdout, stderr = ssh.exec_command("cat /opt/hairos-bot/bot.py")
content = stdout.read().decode('utf-8')

# Remove admin_menu button from cmd_start
content = content.replace(
    '        kb = InlineKeyboardMarkup(list(main_menu_kb().inline_keyboard) + [\n            [InlineKeyboardButton("\u2699\ufe0f \u0410\u0434\u043c\u0438\u043d-\u043f\u0430\u043d\u0435\u043b\u044c", callback_data="admin_menu")],\n        ])',
    '        kb = main_menu_kb()'
)

# Remove admin_menu from back_main handler
content = content.replace(
    '            kb = InlineKeyboardMarkup(list(main_menu_kb().inline_keyboard) + [\n                [InlineKeyboardButton("\u2699\ufe0f \u0410\u0434\u043c\u0438\u043d-\u043f\u0430\u043d\u0435\u043b\u044c", callback_data="admin_menu")],\n            ])',
    '            kb = main_menu_kb()'
)

# Write back
sftp = ssh.open_sftp()
f = sftp.open('/opt/hairos-bot/bot.py', 'w')
f.write(content.encode('utf-8'))
f.close()
sftp.close()
print("Admin panel removed from bot")

# Restart bot
stdin, stdout, stderr = ssh.exec_command('systemctl restart hairos-polling')
stdout.channel.recv_exit_status()
print("Bot restarted")

ssh.close()
print("Done!")
