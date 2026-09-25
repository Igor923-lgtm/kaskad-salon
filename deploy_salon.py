"""
deploy_salon.py — Автоматический деплой нового салона на сервер.

Использование:
    python deploy_salon.py

Скрипт запросит все данные и развернет новый салон на сервере.
"""

import paramiko
import os
import sys
import json

# ── Конфигурация сервера (запрашивается при запуске) ──
SERVER_HOST = None
SERVER_USER = None
SERVER_PASS = None
KASKAD_DIR = "/opt/kaskad-multitenant"  # Рабочий код (источник)


def get_input(prompt, default=""):
    """Получить ввод от пользователя с дефолтным значением."""
    if default:
        val = input(f"{prompt} [{default}]: ").strip()
        return val if val else default
    return input(f"{prompt}: ").strip()


def connect_ssh():
    """Подключиться к серверу."""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(SERVER_HOST, username=SERVER_USER, password=SERVER_PASS, timeout=15)
    return ssh


def run_cmd(ssh, cmd):
    """Выполнить команду на сервере."""
    stdin, stdout, stderr = ssh.exec_command(cmd)
    stdout.channel.recv_exit_status()
    return stdout.read().decode(), stderr.read().decode()


def main():
    global SERVER_HOST, SERVER_USER, SERVER_PASS

    print("=" * 50)
    print("  ДЕПЛОЙ НОВОГО САЛОНА")
    print("=" * 50)
    print()

    # ── Конфигурация сервера ──
    print("── Данные сервера ──")
    SERVER_HOST = get_input("IP сервера")
    SERVER_USER = get_input("Логин", "root")
    SERVER_PASS = get_input("Пароль")

    # ── Собираем данные ──
    print("── Основные данные салона ──")
    salon_id = get_input("ID салона (латиницей, напр. hairos)")
    salon_name = get_input("Название салона")
    salon_address = get_input("Адрес")
    salon_phone = get_input("Телефон основной")
    salon_phone2 = get_input("Телефон дополнительный", "")
    salon_metro = get_input("Метро", "")
    salon_map_url = get_input("Ссылка на Яндекс Карты", "")
    salon_whatsapp = get_input("WhatsApp", salon_phone)
    salon_timezone = get_input("Часовой пояс", "Europe/Minsk")
    crm_password = get_input("Пароль CRM")

    print("\n── Часы работы ──")
    hours_start = get_input("Будни: начало", "10")
    hours_end = get_input("Будни: конец", "22")
    sat_start = get_input("Суббота: начало", hours_start)
    sat_end = get_input("Суббота: конец", hours_end)
    sun_start = get_input("Воскресенье: начало", hours_start)
    sun_end = get_input("Воскресенье: конец", hours_end)

    print("\n── Telegram ──")
    bot_token = get_input("Токен бота")
    admin_tg_id = get_input("Telegram ID администратора", "")

    print("\n── Мастера (введите 'стоп' когда закончите) ──")
    masters = []
    while True:
        name = input(f"\nИмя мастера #{len(masters)+1} (или 'стоп'): ").strip()
        if name.lower() == 'стоп':
            break
        phone = get_input("  Телефон мастера")
        spec = get_input("  Специализация")
        masters.append({"name": name, "phone": phone, "spec": spec})

    print("\n── Услуги (введите 'стоп' когда закончите) ──")
    sections = []
    while True:
        title = input(f"\nНазвание раздела #{len(sections)+1} (или 'стоп'): ").strip()
        if title.lower() == 'стоп':
            break
        services = []
        while True:
            svc_name = input(f"  Услуга (или 'стоп' для следующего раздела): ").strip()
            if svc_name.lower() == 'стоп':
                break
            svc_price = get_input("  Цена")
            services.append((svc_name, svc_price))
        sections.append({"title": title, "services": services})

    print("\n── Логотип ──")
    logo_path = get_input("Путь к файлу логотипа (или Enter для пропуска)", "")

    print("\n── Фото работ ──")
    works_dir = get_input("Путь к папке с фото работ (или Enter для пропуска)", "")

    # ── Порт ──
    port = get_input("Порт CRM", "8006")

    # ── Подтверждение ──
    print("\n" + "=" * 50)
    print(f"  Салон: {salon_name}")
    print(f"  ID: {salon_id}")
    print(f"  Адрес: {salon_address}")
    print(f"  Телефон: {salon_phone}")
    print(f"  Порт: {port}")
    print(f"  Мастеров: {len(masters)}")
    print(f"  Разделов услуг: {len(sections)}")
    print("=" * 50)

    confirm = input("\nНачать деплой? (да/нет): ").strip().lower()
    if confirm != 'да':
        print("Отменено.")
        return

    # ── Деплой ──
    print("\n🚀 Начинаю деплой...")
    ssh = connect_ssh()
    bot_dir = f"/opt/{salon_id}-bot"

    # 1. Создаём директории
    print("[1/8] Создаю директории...")
    for d in [bot_dir, f"{bot_dir}/templates", f"{bot_dir}/static",
              f"{bot_dir}/salons/{salon_id}", f"{bot_dir}/works_photos"]:
        run_cmd(ssh, f"mkdir -p {d}")

    # 2. Копируем код из КАСКАДа
    print("[2/8] Копирую код из КАСКАДа...")
    run_cmd(ssh, f"cp {KASKAD_DIR}/*.py {bot_dir}/")
    run_cmd(ssh, f"cp {KASKAD_DIR}/requirements.txt {bot_dir}/")
    run_cmd(ssh, f"cp {KASKAD_DIR}/templates/*.html {bot_dir}/templates/")
    run_cmd(ssh, f"cp {KASKAD_DIR}/static/* {bot_dir}/static/")

    # 3. Генерируем .env
    print("[3/8] Генерирую .env...")
    env_content = f"""# === Салон ===
SALON_ID={salon_id}

# === Telegram ===
BOT_TOKEN={bot_token}
ADMIN_IDS={admin_tg_id}

# === База данных ===
DB_PATH=bot_cache.db

# === CRM ===
CRM_PASSWORD={crm_password}
CRM_API_URL=

# === Прокси ===
SOCKS5_PROXY=

# === Салон: информация ===
SALON_NAME={salon_name}
SALON_ADDRESS={salon_address}
SALON_PHONE={salon_phone}
SALON_PHONE_SECONDARY={salon_phone2}
SALON_METRO={salon_metro}
SALON_MAP_URL={salon_map_url}
SALON_WHATSAPP={salon_whatsapp}

# === Салон: часы работы ===
SALON_HOURS_START={hours_start}
SALON_HOURS_END={hours_end}
SALON_HOURS_SAT_START={sat_start}
SALON_HOURS_SAT_END={sat_end}
SALON_HOURS_SUN_START={sun_start}
SALON_HOURS_SUN_END={sun_end}

# === Часовой пояс ===
SALON_TIMEZONE={salon_timezone}

# === Функции салона ===
DISCOUNTS_ENABLED=true
BIRTHDAY_DISCOUNT=true
REVIEW_DISCOUNT=true
GALLERY_ENABLED=true
MASTERS_ENABLED=true
RATING_ENABLED=true
MY_BOOKINGS_ENABLED=true
HISTORY_ENABLED=true
BIRTHDAY_ENABLED=true
CONTACT_ENABLED=true
WIDGET_ENABLED=true
"""
    sftp = ssh.open_sftp()
    f = sftp.open(f"{bot_dir}/salons/{salon_id}/.env", 'w')
    f.write(env_content.encode('utf-8'))
    f.close()

    # 4. Заменяем данные в bot.py
    print("[4/8] Заменяю данные в bot.py...")
    stdin, stdout, stderr = ssh.exec_command(f"cat {bot_dir}/bot.py")
    bot_content = stdout.read().decode('utf-8')

    # Замена адреса
    bot_content = bot_content.replace('Кальварийская ул., 52', salon_address.split(',')[0] if ',' in salon_address else salon_address)
    bot_content = bot_content.replace('(цокольный этаж)', '')
    # Замена телефона
    bot_content = bot_content.replace('+375 29 120-61-01', salon_phone)
    bot_content = bot_content.replace('+375 (17) 350-81-91', salon_phone2)
    bot_content = bot_content.replace('tel:+375291206101', f'tel:{salon_phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")}')
    # Замена часов
    bot_content = bot_content.replace('Пн-Пт: 10:00 \u2013 21:00', f'Ежедневно: {hours_start}:00 \u2013 {hours_end}:00')
    bot_content = bot_content.replace('Сб: 11:00 \u2013 20:00', '')
    bot_content = bot_content.replace('Вс: 11:00 \u2013 17:00', '')
    # Замена метро
    bot_content = bot_content.replace('Молодёжная (680 м)', salon_metro)
    # Замена карты
    bot_content = bot_content.replace('kaskad/1176196517', salon_map_url.split('/')[-2] if salon_map_url else '')
    # Замена названия
    bot_content = bot_content.replace('KASKAD', salon_name)
    bot_content = bot_content.replace('КАСКАД', salon_name)

    f = sftp.open(f"{bot_dir}/bot.py", 'w')
    f.write(bot_content.encode('utf-8'))
    f.close()

    # 5. Заменяем данные в шаблонах
    print("[5/8] Заменяю данные в шаблонах...")
    for tpl in ['*.html', 'manifest.json', 'style.css']:
        run_cmd(ssh, f"sed -i 's/KASKAD CRM/{salon_name} CRM/g' {bot_dir}/templates/{tpl} {bot_dir}/static/{tpl} 2>/dev/null")
        run_cmd(ssh, f"sed -i 's/KASKAD/{salon_name}/g' {bot_dir}/templates/{tpl} {bot_dir}/static/{tpl} 2>/dev/null")

    # Заменяем куку в api.py
    run_cmd(ssh, f"sed -i 's/crm_token/{salon_id}_token/g' {bot_dir}/api.py")

    # 6. Генерируем price_data.py
    print("[6/8] Генерирую прайс-лист...")
    price_content = '"""Прайс-лист салона «' + salon_name + '»."""\n\nPRICE_SECTIONS = [\n'
    for section in sections:
        price_content += '    {\n'
        price_content += f'        "title": "{section["title"]}",\n'
        price_content += '        "services": [\n'
        for svc_name, svc_price in section['services']:
            # Try to convert price to int
            try:
                price_val = int(svc_price)
                price_content += f'            ("{svc_name}", {price_val}),\n'
            except ValueError:
                price_content += f'            ("{svc_name}", "{svc_price}"),\n'
        price_content += '        ],\n'
        price_content += '    },\n'
    price_content += ']\n\n\ndef format_price(price):\n    if isinstance(price, int):\n        return f"{price} BYN"\n    return str(price)\n\n\ndef format_section(section):\n    text = f"**{section[\'title\']}**\\n"\n    if section.get("note"):\n        text += f"_{section[\'note\']}_\\n\\n"\n    else:\n        text += "\\n"\n    for name, price in section["services"]:\n        text += f"• {name} — {format_price(price)}\\n"\n    return text\n'

    f = sftp.open(f"{bot_dir}/price_data.py", 'w')
    f.write(price_content.encode('utf-8'))
    f.close()

    # 7. Загружаем логотип и фото
    if logo_path and os.path.exists(logo_path):
        print("[7/8] Загружаю логотип...")
        sftp.put(logo_path, f'{bot_dir}/logo.png')
        sftp.put(logo_path, f'{bot_dir}/static/logo.png')

    if works_dir and os.path.isdir(works_dir):
        print("[7/8] Загружаю фото работ...")
        for photo in os.listdir(works_dir):
            photo_path = os.path.join(works_dir, photo)
            if os.path.isfile(photo_path):
                try:
                    sftp.put(photo_path, f'{bot_dir}/works_photos/{photo}')
                except Exception as e:
                    print(f"  Пропуск {photo}: {e}")

    sftp.close()

    # 8. Создаём сервисы и запускаем
    print("[8/8] Создаю сервисы и запускаю...")

    # venv
    run_cmd(ssh, f"cd {bot_dir} && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt 2>&1")

    # systemd: CRM
    crm_service = f"""[Unit]
Description={salon_name} CRM
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory={bot_dir}
Environment=SALON_ID={salon_id}
ExecStart={bot_dir}/venv/bin/python3 -m uvicorn api:app --host 0.0.0.0 --port {port}
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
"""
    sftp = ssh.open_sftp()
    f = sftp.open(f'/etc/systemd/system/{salon_id}-crm.service', 'w')
    f.write(crm_service.encode('utf-8'))
    f.close()

    # systemd: Bot polling
    bot_service = f"""[Unit]
Description={salon_name} Bot Polling
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory={bot_dir}
Environment=SALON_ID={salon_id}
ExecStart={bot_dir}/venv/bin/python3 bot.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
"""
    f = sftp.open(f'/etc/systemd/system/{salon_id}-polling.service', 'w')
    f.write(bot_service.encode('utf-8'))
    f.close()
    sftp.close()

    # Инициализация БД и мастеров
    init_script = f"""
import asyncio
import aiosqlite

async def main():
    db = await aiosqlite.connect('{bot_dir}/bot_cache.db')
    
    # Create tables
    await db.execute('''CREATE TABLE IF NOT EXISTS masters (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
        specialization TEXT DEFAULT '', description TEXT DEFAULT '',
        categories TEXT DEFAULT '', photo_file_id TEXT DEFAULT '',
        phone TEXT DEFAULT '', telegram_id INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1, commission_percent INTEGER DEFAULT 50
    )''')
    await db.execute('''CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT, master_name TEXT NOT NULL,
        date TEXT NOT NULL, time TEXT NOT NULL, client_name TEXT DEFAULT '',
        phone TEXT DEFAULT '', telegram_id INTEGER DEFAULT 0,
        service_name TEXT DEFAULT '', price TEXT DEFAULT '',
        confirmed INTEGER DEFAULT 0, completed INTEGER DEFAULT 0,
        cancelled INTEGER DEFAULT 0, reminder_sent INTEGER DEFAULT 0,
        reminder_2h_sent INTEGER DEFAULT 0, reminder_repeat_sent INTEGER DEFAULT 0,
        review_sent INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime('now'))
    )''')
    await db.execute('''CREATE TABLE IF NOT EXISTS clients (
        telegram_id INTEGER PRIMARY KEY, name TEXT DEFAULT '',
        phone TEXT DEFAULT '', birthday TEXT DEFAULT '',
        client_type TEXT DEFAULT 'lead', discount_percent INTEGER DEFAULT 0,
        visit_count INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )''')
    await db.execute('''CREATE TABLE IF NOT EXISTS master_schedule (
        id INTEGER PRIMARY KEY AUTOINCREMENT, master_name TEXT NOT NULL,
        day_of_week INTEGER NOT NULL, start_time TEXT DEFAULT '10:00',
        end_time TEXT DEFAULT '22:00', is_day_off INTEGER DEFAULT 0,
        selected_hours TEXT DEFAULT '', UNIQUE(master_name, day_of_week)
    )''')
    await db.execute('''CREATE TABLE IF NOT EXISTS master_date_schedule (
        id INTEGER PRIMARY KEY AUTOINCREMENT, master_name TEXT NOT NULL,
        date TEXT NOT NULL, time_slots TEXT DEFAULT '',
        is_day_off INTEGER DEFAULT 0, UNIQUE(master_name, date)
    )''')
    await db.execute('''CREATE TABLE IF NOT EXISTS master_sessions (
        token TEXT PRIMARY KEY, master_id INTEGER, master_name TEXT,
        telegram_id INTEGER, expires TEXT
    )''')
    await db.execute('''CREATE TABLE IF NOT EXISTS client_notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, client_telegram_id INTEGER,
        author TEXT DEFAULT '', text TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now'))
    )''')
    await db.execute('''CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT, master_name TEXT,
        client_name TEXT, score INTEGER, created_at TEXT DEFAULT (datetime('now'))
    )''')
    await db.execute('''CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, booking_id INTEGER DEFAULT 0,
        master_name TEXT DEFAULT '', service_name TEXT DEFAULT '',
        amount REAL DEFAULT 0, payment_type TEXT DEFAULT 'cash',
        created_at TEXT DEFAULT (datetime('now'))
    )''')
    await db.execute('''CREATE TABLE IF NOT EXISTS salon_settings (
        key TEXT PRIMARY KEY, value TEXT DEFAULT ''
    )''')
    await db.execute('''CREATE TABLE IF NOT EXISTS discounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER,
        percent INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime('now'))
    )''')
    await db.execute('''CREATE TABLE IF NOT EXISTS content (
        key TEXT PRIMARY KEY, value TEXT DEFAULT ''
    )''')
    
    # Add masters
"""
    for i, m in enumerate(masters):
        init_script += f'    await db.execute("INSERT INTO masters (name, specialization, phone) VALUES (?,?,?)", ("{m["name"]}", "{m["spec"]}", "{m["phone"]}"))\n'
        init_script += f'    print(f"  Мастер {m[chr(110)+chr(97)+chr(109)+chr(101)]} добавлен")\n'
    
    init_script += """
    # Add default schedule for all masters (all days working)
"""
    for m in masters:
        init_script += f'    for dow in range(7):\n'
        init_script += f'        await db.execute("INSERT OR IGNORE INTO master_schedule (master_name, day_of_week, start_time, end_time, is_day_off) VALUES (?,?,?,?,?)", ("{m["name"]}", dow, "10:00", "22:00", 0))\n'
    
    init_script += """
    await db.commit()
    await db.close()
    print("БД инициализирована")

asyncio.run(main())
"""
    
    # Write and run init script
    sftp = ssh.open_sftp()
    f = sftp.open(f'{bot_dir}/init_salon.py', 'w')
    f.write(init_script.encode('utf-8'))
    f.close()
    sftp.close()
    
    run_cmd(ssh, f"cd {bot_dir} && source venv/bin/activate && python3 init_salon.py")

    # Start services
    run_cmd(ssh, "systemctl daemon-reload")
    run_cmd(ssh, f"systemctl enable {salon_id}-crm {salon_id}-polling")
    run_cmd(ssh, f"systemctl start {salon_id}-crm {salon_id}-polling")

    import time
    time.sleep(3)

    # Verify
    out, _ = run_cmd(ssh, f"systemctl is-active {salon_id}-crm {salon_id}-polling")
    statuses = out.strip().split('\n')

    ssh.close()

    print("\n" + "=" * 50)
    print("  ✅ ДЕПЛОЙ ЗАВЕРШЁН!")
    print("=" * 50)
    print(f"\n  CRM: http://{SERVER_HOST}:{port}/login")
    print(f"  Пароль: {crm_password}")
    print(f"  Мастера: http://{SERVER_HOST}:{port}/master")
    print(f"  Бот: {'активен' if 'active' in statuses[1] else 'ОШИБКА'}")
    print(f"  CRM: {'активна' if 'active' in statuses[0] else 'ОШИБКА'}")
    print()


if __name__ == "__main__":
    main()
