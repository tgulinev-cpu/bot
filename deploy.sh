#!/bin/bash

# Скрипт развертывания бота на сервере через Termius

echo "🚀 Начало развертывания Delivery Bot..."

# 1. Обновление системы
echo "📦 Обновление пакетов..."
sudo apt update && sudo apt upgrade -y

# 2. Установка Docker и Docker Compose
echo "🐳 Установка Docker..."
sudo apt install -y docker.io docker-compose

# 3. Клонирование репозитория
echo "📂 Клонирование репозитория..."
git clone https://github.com/yourusername/delivery-bot.git
cd delivery-bot

# 4. Создание файла окружения
echo "🔧 Настройка окружения..."
read -p "Введите токен вашего бота: " BOT_TOKEN

cat > .env << EOF
BOT_TOKEN=$BOT_TOKEN
EOF

# 5. Создание директории для данных
echo "💾 Создание директорий..."
mkdir -p data
chmod 777 data

# 6. Запуск контейнера
echo "🚀 Запуск бота..."
sudo docker-compose up -d

# 7. Проверка статуса
echo "🔍 Проверка статуса..."
sudo docker-compose ps

echo "✅ Развертывание завершено!"
echo "📋 Инструкция:"
echo "1. Проверить логи: sudo docker-compose logs -f"
echo "2. Остановить бота: sudo docker-compose down"
echo "3. Обновить бота: git pull && sudo docker-compose up -d --build"
