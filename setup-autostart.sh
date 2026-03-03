#!/bin/bash
# Установка автозапуска Email Processor при перезагрузке Debian
# Запускать с правами root: sudo bash setup-autostart.sh

echo "Настройка автозапуска Email Processor..."

# 1. Включаем автозапуск Docker
echo "1. Включаем автозапуск Docker..."
systemctl enable docker
systemctl start docker

# 2. Создаем systemd unit для проекта
echo "2. Создаем systemd unit..."
cat > /etc/systemd/system/docker-compose-project1.service << 'EOF'
[Unit]
Description=Email Processor Docker Compose
Requires=docker.service
After=docker.service network.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/root/project1
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

# 3. Перезагружаем systemd и включаем сервис
echo "3. Активируем сервис..."
systemctl daemon-reload
systemctl enable docker-compose-project1
systemctl start docker-compose-project1

# 4. Проверяем статус
echo "4. Проверка статуса..."
systemctl is-active docker-compose-project1 && echo "✅ Сервис запущен" || echo "❌ Ошибка запуска"
systemctl is-enabled docker-compose-project1 && echo "✅ Автозапуск включен" || echo "❌ Автозапуск не включен"

echo ""
echo "Настройка завершена!"
echo "При перезагрузке Debian все контейнеры запустятся автоматически."
echo ""
echo "Команды для проверки:"
echo "  systemctl status docker-compose-project1"
echo "  docker compose -f /root/project1/docker-compose.yml ps"
