#!/bin/bash
# deploy_all.sh — Единый скрипт деплоя всех проектов на новый Ubuntu сервер.
#
# Использование:
#   1. Загрузите этот скрипт на сервер
#   2. Запустите: bash deploy_all.sh
#
# Что делает:
#   1. Устанавливает Python 3 и зависимости
#   2. Загружает код проекта (через git или scp)
#   3. Создаёт .env файлы из шаблонов
#   4. Устанавливает Python пакеты
#   5. Создаёт systemd сервисы
#   6. Запускает все сервисы
#   7. Настраивает автоматические бэкапы

set -e

# ── Конфигурация ──
SERVICES=("kaskad:8000:Europe/Moscow" "hairos:8005:Europe/Minsk")
BACKUP_DIR="/opt/backups"
BACKUP_RETENTION_DAYS=7

echo "============================================"
echo "  ДЕПЛОЙ: kaskad + hairos"
echo "============================================"

# ── Шаг 1: Системные зависимости ──
echo ""
echo "[1/7] Установка системных зависимостей..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv curl

PYTHON_VERSION=$(python3 --version)
echo "  OK: $PYTHON_VERSION"

# ── Шаг 2: Загрузка кода ──
echo ""
echo "[2/7] Загрузка кода..."

# Вариант A: Если код уже загружен через scp/git
if [ -d "/opt/kaskad-multitenant" ]; then
    echo "  Код уже есть в /opt/kaskad-multitenant"
else
    echo "  ВНИМАНИЕ: Загрузите код в /opt/kaskad-multitenant"
    echo "  scp -r ./kaskad-multitenant root@$(hostname -I | awk '{print $1}'):/opt/"
    echo "  Или: git clone <repo> /opt/kaskad-multitenant"
    exit 1
fi

# ── Шаг 3: Настройка сервисов ──
echo ""
echo "[3/7] Настройка сервисов..."

for SVC_CONFIG in "${SERVICES[@]}"; do
    IFS=':' read -r SVC_ID SVC_PORT SVC_TZ <<< "$SVC_CONFIG"
    SVC_DIR="/opt/${SVC_ID}-bot"

    echo "  --- $SVC_ID (порт $SVC_PORT) ---"

    # Создаём директории
    mkdir -p "$SVC_DIR/data" "$SVC_DIR/templates" "$SVC_DIR/static" "$SVC_DIR/works_photos"

    # Копируем код
    cp /opt/kaskad-multitenant/bot.py "$SVC_DIR/"
    cp /opt/kaskad-multitenant/db.py "$SVC_DIR/"
    cp /opt/kaskad-multitenant/config.py "$SVC_DIR/"
    cp /opt/kaskad-multitenant/api.py "$SVC_DIR/"
    cp /opt/kaskad-multitenant/price_data.py "$SVC_DIR/"
    cp /opt/kaskad-multitenant/requirements.txt "$SVC_DIR/"
    cp /opt/kaskad-multitenant/price.json "$SVC_DIR/" 2>/dev/null || true

    # Копируем шаблоны и статику
    cp -r /opt/kaskad-multitenant/templates/* "$SVC_DIR/templates/" 2>/dev/null || true
    cp -r /opt/kaskad-multitenant/static/* "$SVC_DIR/static/" 2>/dev/null || true
    cp /opt/kaskad-multitenant/logo.png "$SVC_DIR/" 2>/dev/null || true

    # Копируем .env (если ещё нет)
    if [ ! -f "$SVC_DIR/.env" ]; then
        if [ -f "/opt/kaskad-multitenant/salons/${SVC_ID}/.env" ]; then
            cp "/opt/kaskad-multitenant/salons/${SVC_ID}/.env" "$SVC_DIR/.env"
        elif [ -f "/opt/kaskad-multitenant/.env.example" ]; then
            cp "/opt/kaskad-multitenant/.env.example" "$SVC_DIR/.env"
            echo "    ВНИМАНИЕ: Отредактируйте $SVC_DIR/.env"
        fi
    fi
    echo "    .env: OK"

    # Создаём venv
    python3 -m venv "$SVC_DIR/venv"
    source "$SVC_DIR/venv/bin/activate"
    pip install --upgrade pip -q
    pip install -r "$SVC_DIR/requirements.txt" -q
    deactivate
    echo "    venv: OK"

    # Создаём systemd сервис CRM
    cat > "/etc/systemd/system/${SVC_ID}-crm.service" << EOF
[Unit]
Description=${SVC_ID} CRM
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${SVC_DIR}
Environment=SALON_ID=${SVC_ID}
ExecStart=${SVC_DIR}/venv/bin/python3 -m uvicorn api:app --host 0.0.0.0 --port ${SVC_PORT}
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1
Environment=TZ=${SVC_TZ}

[Install]
WantedBy=multi-user.target
EOF

    # Создаём systemd сервис Bot
    cat > "/etc/systemd/system/${SVC_ID}-polling.service" << EOF
[Unit]
Description=${SVC_ID} Bot Polling
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${SVC_DIR}
Environment=SALON_ID=${SVC_ID}
ExecStart=${SVC_DIR}/venv/bin/python3 bot.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1
Environment=TZ=${SVC_TZ}

[Install]
WantedBy=multi-user.target
EOF

    echo "    systemd: OK"
done

# ── Шаг 4: Запуск сервисов ──
echo ""
echo "[4/7] Запуск сервисов..."
systemctl daemon-reload

for SVC_CONFIG in "${SERVICES[@]}"; do
    IFS=':' read -r SVC_ID SVC_PORT SVC_TZ <<< "$SVC_CONFIG"
    systemctl enable "${SVC_ID}-crm" "${SVC_ID}-polling"
    systemctl start "${SVC_ID}-crm" "${SVC_ID}-polling"
    echo "  $SVC_ID: запущен"
done

# ── Шаг 5: Настройка бэкапов ──
echo ""
echo "[5/7] Настройка автоматических бэкапов..."
mkdir -p "$BACKUP_DIR"

cat > /opt/backup_all.sh << 'BACKUP_EOF'
#!/bin/bash
BACKUP_DIR=/opt/backups
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR
for dir in /opt/*/bot_cache.db; do
    if [ -f "$dir" ]; then
        name=$(basename $(dirname $dir))
        cp "$dir" "$BACKUP_DIR/${name}_${DATE}.db"
    fi
done
find $BACKUP_DIR -name "*.db" -mtime +7 -delete
BACKUP_EOF

chmod +x /opt/backup_all.sh

# Добавляем cron (если ещё нет)
(crontab -l 2>/dev/null | grep -v backup_all; echo "0 3 * * * /opt/backup_all.sh") | crontab -
echo "  cron: OK (ежедневно в 3:00)"

# ── Шаг 6: Проверка ──
echo ""
echo "[6/7] Проверка..."
sleep 5

for SVC_CONFIG in "${SERVICES[@]}"; do
    IFS=':' read -r SVC_ID SVC_PORT SVC_TZ <<< "$SVC_CONFIG"
    STATUS=$(systemctl is-active "${SVC_ID}-crm" "${SVC_ID}-polling" 2>/dev/null | tr '\n' ' ')
    HEALTH=$(curl -s "http://localhost:${SVC_PORT}/health" --connect-timeout 5 2>/dev/null || echo '{"status":"error"}')
    echo "  $SVC_ID: $STATUS | health: $HEALTH"
done

# ── Шаг 7: Информация ──
echo ""
echo "[7/7] Готово!"
echo ""
echo "============================================"
echo "  ДЕПЛОЙ ЗАВЕРШЁН"
echo "============================================"
echo ""
echo "  Сервисы:"
for SVC_CONFIG in "${SERVICES[@]}"; do
    IFS=':' read -r SVC_ID SVC_PORT SVC_TZ <<< "$SVC_CONFIG"
    echo "    $SVC_ID: http://$(hostname -I | awk '{print $1}'):${SVC_PORT}/login"
done
echo ""
echo "  Бэкапы: /opt/backups/ (cron: 3:00 daily, 7 дней)"
echo ""
echo "  НЕ ЗАБУДЬТЕ:"
echo "  1. Проверить .env файлы в /opt/*/bot_cache.db"
echo "  2. Загрузить базы данных (bot_cache.db)"
echo "  3. Настроить DNS (вместо IP-адресов)"
echo ""
