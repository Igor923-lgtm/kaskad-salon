import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

# Read bot.py
stdin, stdout, stderr = ssh.exec_command("cat /opt/hairos-bot/bot.py")
content = stdout.read().decode('utf-8')

# Replace cb_book function to skip gender selection
old_cb_book = '''async def cb_book(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    log.info(f"BOOK: cb_book called, user={query.from_user.id}")
    nav_push(ctx, MAIN_MENU)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("\\U0001f469 Женщине", callback_data="gender_f")],
        [InlineKeyboardButton("\\U0001f468 Мужчине", callback_data="gender_m")],
        [InlineKeyboardButton("\\u25c0\\ufe0f Назад", callback_data="back_step")],
    ])
    ctx.user_data["booking"] = {}
    await query.edit_message_text("Кому записываемся?", reply_markup=kb)
    return BOOK_SELECT_GENDER'''

new_cb_book = '''async def cb_book(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    log.info(f"BOOK: cb_book called, user={query.from_user.id}")
    nav_push(ctx, MAIN_MENU)
    ctx.user_data["booking"] = {"gender": "f"}
    # Skip gender selection, go directly to services for women
    sections = price_data.PRICE_SECTIONS
    kb = []
    for i, section in enumerate(sections):
        title = section["title"]
        if not any(kw in title.lower() for kw in ["мужск", "барбер"]):
            kb.append([InlineKeyboardButton(title[:40], callback_data=f"book_sec_{i}")])
    if not kb:
        kb.append([InlineKeyboardButton("Нет услуг", callback_data="back_main")])
    else:
        kb.append([InlineKeyboardButton("\\u25c0\\ufe0f Назад", callback_data="back_step")])
    await query.edit_message_text("Выберите раздел услуг:", reply_markup=InlineKeyboardMarkup(kb))
    return BOOK_SELECT_SERVICE'''

content = content.replace(old_cb_book, new_cb_book)

# Write back
sftp = ssh.open_sftp()
f = sftp.open('/opt/hairos-bot/bot.py', 'w')
f.write(content.encode('utf-8'))
f.close()
sftp.close()

print("cb_book updated - gender selection removed")

# Restart
stdin, stdout, stderr = ssh.exec_command('systemctl restart hairos-polling')
stdout.channel.recv_exit_status()
print("Bot restarted")

ssh.close()
print("Done!")
