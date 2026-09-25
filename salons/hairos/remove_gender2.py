import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

# Read bot.py
stdin, stdout, stderr = ssh.exec_command("cat /opt/hairos-bot/bot.py")
content = stdout.read().decode('utf-8')

# Find and replace the cb_book function
# The function starts at "async def cb_book" and ends before "async def book_select_gender"
start_marker = 'async def cb_book(update: Update, ctx: ContextTypes.DEFAULT_TYPE):'
end_marker = 'async def book_select_gender(update: Update, ctx: ContextTypes.DEFAULT_TYPE):'

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx == -1 or end_idx == -1:
    print(f"ERROR: Could not find markers. start={start_idx}, end={end_idx}")
else:
    # New function that skips gender selection
    new_func = '''async def cb_book(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    log.info(f"BOOK: cb_book called, user={query.from_user.id}")
    nav_push(ctx, MAIN_MENU)
    ctx.user_data["booking"] = {"gender": "f"}
    # Skip gender selection, go directly to services
    sections = price_data.PRICE_SECTIONS
    kb = []
    for i, section in enumerate(sections):
        title = section["title"]
        if not any(kw in title.lower() for kw in ["\u043c\u0443\u0436\u0441\u043a", "\u0431\u0430\u0440\u0431\u0435\u0440"]):
            kb.append([InlineKeyboardButton(title[:40], callback_data=f"book_sec_{i}")])
    if not kb:
        kb.append([InlineKeyboardButton("\u041d\u0435\u0442 \u0443\u0441\u043b\u0443\u0433", callback_data="back_main")])
    else:
        kb.append([InlineKeyboardButton("\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data="back_step")])
    await query.edit_message_text("\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0440\u0430\u0437\u0434\u0435\u043b \u0443\u0441\u043b\u0443\u0433:", reply_markup=InlineKeyboardMarkup(kb))
    return BOOK_SELECT_SERVICE

'''
    
    content = content[:start_idx] + new_func + content[end_idx:]
    
    # Write back
    sftp = ssh.open_sftp()
    f = sftp.open('/opt/hairos-bot/bot.py', 'w')
    f.write(content.encode('utf-8'))
    f.close()
    sftp.close()
    
    print("cb_book function replaced successfully")

# Restart
stdin, stdout, stderr = ssh.exec_command('systemctl restart hairos-polling')
stdout.channel.recv_exit_status()
print("Bot restarted")

ssh.close()
print("Done!")
