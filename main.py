#!/usr/bin/env python3
"""
Telegram Bot: Delivery Orders Game
Version: 1.0.0
Author: Delivery Game Bot
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import json
import random
import hashlib
from enum import Enum

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters,
    ContextTypes
)
from telegram.constants import ParseMode

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
class States(Enum):
    MAIN_MENU = 1
    JOIN_GAME = 2
    CREATE_GAME = 3
    IN_GAME = 4
    SELECT_ORDERS = 5
    ADD_NOTE = 6
    VIEW_STATS = 7
    VIEW_NOTES = 8
    GAME_ROOM = 9
    WAITING_FOR_PLAYERS = 10

# Модели данных
class Player:
    def __init__(self, user_id: int, username: str = ""):
        self.user_id = user_id
        self.username = username
        self.orders_taken = 0
        self.total_orders = 0
        self.notes: List[str] = []
        self.joined_at = datetime.now()
        self.last_activity = datetime.now()
        self.hourly_stats: Dict[str, int] = {}  # час -> количество заказов
    
    def to_dict(self) -> Dict:
        return {
            'user_id': self.user_id,
            'username': self.username,
            'orders_taken': self.orders_taken,
            'total_orders': self.total_orders,
            'notes': self.notes,
            'joined_at': self.joined_at.isoformat(),
            'last_activity': self.last_activity.isoformat(),
            'hourly_stats': self.hourly_stats
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Player':
        player = cls(data['user_id'], data.get('username', ''))
        player.orders_taken = data.get('orders_taken', 0)
        player.total_orders = data.get('total_orders', 0)
        player.notes = data.get('notes', [])
        player.joined_at = datetime.fromisoformat(data['joined_at'])
        player.last_activity = datetime.fromisoformat(data['last_activity'])
        player.hourly_stats = data.get('hourly_stats', {})
        return player

class GameRoom:
    def __init__(self, room_id: str, creator_id: int, max_players: int = 2):
        self.room_id = room_id
        self.creator_id = creator_id
        self.players: Dict[int, Player] = {}
        self.max_players = max_players
        self.status = "waiting"  # waiting, active, finished
        self.created_at = datetime.now()
        self.current_orders: List[Dict] = []
        self.game_duration = 3600  # 1 час в секундах
        self.end_time: Optional[datetime] = None
        self.stats_sent_at: Optional[datetime] = None
    
    def add_player(self, player: Player) -> bool:
        if len(self.players) >= self.max_players:
            return False
        if player.user_id in self.players:
            return False
        self.players[player.user_id] = player
        return True
    
    def remove_player(self, user_id: int) -> bool:
        return bool(self.players.pop(user_id, None))
    
    def start_game(self):
        self.status = "active"
        self.end_time = datetime.now() + timedelta(seconds=self.game_duration)
        self.generate_orders()
    
    def generate_orders(self):
        """Генерация случайных заказов для текущего раунда"""
        self.current_orders = []
        num_orders = random.randint(1, 3)
        
        addresses = [
            "ул. Ленина, 15",
            "пр. Мира, 42",
            "ул. Советская, 7",
            "пр. Победы, 33",
            "ул. Центральная, 21",
            "пр. Строителей, 8",
            "ул. Садовая, 12",
            "пр. Космонавтов, 5"
        ]
        
        for _ in range(num_orders):
            order = {
                'id': hashlib.md5(str(datetime.now()).encode()).hexdigest()[:8],
                'address': random.choice(addresses),
                'weight': random.randint(1, 20),
                'price': random.randint(100, 1000),
                'time_limit': random.randint(10, 60)
            }
            self.current_orders.append(order)
    
    def get_leaderboard(self) -> List[Tuple[str, int]]:
        """Получить таблицу лидеров"""
        leaderboard = []
        for player in self.players.values():
            leaderboard.append((player.username or f"Игрок {player.user_id}", player.orders_taken))
        
        leaderboard.sort(key=lambda x: x[1], reverse=True)
        return leaderboard
    
    def get_hourly_stats(self, player_id: int) -> Dict[str, int]:
        """Получить часовую статистику игрока"""
        player = self.players.get(player_id)
        if not player:
            return {}
        
        current_hour = datetime.now().strftime("%Y-%m-%d %H:00")
        return {current_hour: player.hourly_stats.get(current_hour, 0)}
    
    def update_hourly_stats(self, player_id: int):
        """Обновить часовую статистику"""
        player = self.players.get(player_id)
        if not player:
            return
        
        current_hour = datetime.now().strftime("%Y-%m-%d %H:00")
        player.hourly_stats[current_hour] = player.hourly_stats.get(current_hour, 0) + 1
    
    def to_dict(self) -> Dict:
        return {
            'room_id': self.room_id,
            'creator_id': self.creator_id,
            'players': {str(k): v.to_dict() for k, v in self.players.items()},
            'max_players': self.max_players,
            'status': self.status,
            'created_at': self.created_at.isoformat(),
            'current_orders': self.current_orders,
            'game_duration': self.game_duration,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'stats_sent_at': self.stats_sent_at.isoformat() if self.stats_sent_at else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'GameRoom':
        room = cls(data['room_id'], data['creator_id'], data.get('max_players', 2))
        room.players = {
            int(k): Player.from_dict(v) 
            for k, v in data['players'].items()
        }
        room.status = data.get('status', 'waiting')
        room.created_at = datetime.fromisoformat(data['created_at'])
        room.current_orders = data.get('current_orders', [])
        room.game_duration = data.get('game_duration', 3600)
        room.end_time = datetime.fromisoformat(data['end_time']) if data.get('end_time') else None
        room.stats_sent_at = datetime.fromisoformat(data['stats_sent_at']) if data.get('stats_sent_at') else None
        return room

class BotDatabase:
    """Простая база данных в памяти с сохранением в файл"""
    def __init__(self, filename: str = 'database.json'):
        self.filename = filename
        self.game_rooms: Dict[str, GameRoom] = {}
        self.user_sessions: Dict[int, Dict] = {}
        self.load_data()
    
    def save_data(self):
        """Сохранить данные в файл"""
        data = {
            'game_rooms': {
                room_id: room.to_dict()
                for room_id, room in self.game_rooms.items()
            },
            'user_sessions': self.user_sessions
        }
        
        try:
            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving data: {e}")
    
    def load_data(self):
        """Загрузить данные из файла"""
        try:
            with open(self.filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            self.game_rooms = {
                room_id: GameRoom.from_dict(room_data)
                for room_id, room_data in data.get('game_rooms', {}).items()
            }
            self.user_sessions = data.get('user_sessions', {})
        except FileNotFoundError:
            self.game_rooms = {}
            self.user_sessions = {}
        except Exception as e:
            logger.error(f"Error loading data: {e}")
            self.game_rooms = {}
            self.user_sessions = {}
    
    def create_game_room(self, creator_id: int, max_players: int = 2) -> str:
        """Создать новую игровую комнату"""
        room_id = hashlib.md5(f"{creator_id}{datetime.now()}".encode()).hexdigest()[:8]
        
        room = GameRoom(room_id, creator_id, max_players)
        self.game_rooms[room_id] = room
        
        # Добавляем создателя в комнату
        creator = Player(creator_id)
        room.add_player(creator)
        
        self.save_data()
        return room_id
    
    def get_user_room(self, user_id: int) -> Optional[GameRoom]:
        """Получить комнату, в которой находится пользователь"""
        for room in self.game_rooms.values():
            if user_id in room.players:
                return room
        return None
    
    def cleanup_inactive_rooms(self):
        """Очистка неактивных комнат"""
        current_time = datetime.now()
        rooms_to_remove = []
        
        for room_id, room in self.game_rooms.items():
            if room.status == "waiting" and (current_time - room.created_at).seconds > 86400:  # 24 часа
                rooms_to_remove.append(room_id)
            elif room.status == "finished" and (current_time - room.created_at).seconds > 3600:  # 1 час
                rooms_to_remove.append(room_id)
        
        for room_id in rooms_to_remove:
            del self.game_rooms[room_id]
        
        if rooms_to_remove:
            self.save_data()

# Инициализация базы данных
db = BotDatabase()

# Клавиатуры
def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура главного меню"""
    keyboard = [
        [InlineKeyboardButton("🎮 Начать игру", callback_data='start_game')],
        [InlineKeyboardButton("➕ Присоединиться к игре", callback_data='join_game')],
        [InlineKeyboardButton("📊 Статистика", callback_data='view_stats')],
        [InlineKeyboardButton("📝 Мои заметки", callback_data='view_notes')],
        [InlineKeyboardButton("❓ Помощь", callback_data='help')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой Назад"""
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_game_room_keyboard(room_id: str) -> InlineKeyboardMarkup:
    """Клавиатура игровой комнаты"""
    keyboard = [
        [InlineKeyboardButton("📦 Выбрать заказы", callback_data=f'select_orders_{room_id}')],
        [InlineKeyboardButton("📊 Статистика комнаты", callback_data=f'room_stats_{room_id}')],
        [InlineKeyboardButton("📝 Добавить заметку", callback_data=f'add_note_{room_id}')],
        [InlineKeyboardButton("👥 Игроки", callback_data=f'room_players_{room_id}')],
        [InlineKeyboardButton("🚪 Выйти из комнаты", callback_data='leave_room')],
        [InlineKeyboardButton("🔙 Главное меню", callback_data='back_to_main')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_orders_selection_keyboard(orders: List[Dict], room_id: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора заказов"""
    keyboard = []
    
    for i, order in enumerate(orders, 1):
        button_text = f"📦 {i}: {order['address']} ({order['weight']}кг, {order['price']}₽)"
        keyboard.append([InlineKeyboardButton(
            button_text, 
            callback_data=f'take_order_{room_id}_{order["id"]}'
        )])
    
    keyboard.append([InlineKeyboardButton("🔄 Обновить заказы", callback_data=f'refresh_orders_{room_id}')])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=f'back_to_room_{room_id}')])
    
    return InlineKeyboardMarkup(keyboard)

def get_stats_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура статистики"""
    keyboard = [
        [InlineKeyboardButton("📈 Часовая статистика", callback_data='hourly_stats')],
        [InlineKeyboardButton("📊 Общая статистика", callback_data='total_stats')],
        [InlineKeyboardButton("🏆 Лидеры", callback_data='leaders')],
        [InlineKeyboardButton("🔙 Главное меню", callback_data='back_to_main')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_notes_keyboard(notes: List[str]) -> InlineKeyboardMarkup:
    """Клавиатура для заметок"""
    keyboard = []
    
    for i, note in enumerate(notes[:10], 1):  # Показываем первые 10 заметок
        keyboard.append([InlineKeyboardButton(
            f"📝 {i}. {note[:30]}...", 
            callback_data=f'view_note_{i}'
        )])
    
    keyboard.append([InlineKeyboardButton("➕ Добавить заметку", callback_data='add_new_note')])
    keyboard.append([InlineKeyboardButton("🗑️ Очистить все заметки", callback_data='clear_notes')])
    keyboard.append([InlineKeyboardButton("🔙 Главное меню", callback_data='back_to_main')])
    
    return InlineKeyboardMarkup(keyboard)

def get_join_game_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура присоединения к игре"""
    keyboard = []
    
    # Показываем доступные комнаты
    available_rooms = []
    for room_id, room in db.game_rooms.items():
        if room.status == "waiting" and len(room.players) < room.max_players:
            available_rooms.append((room_id, room))
    
    for room_id, room in available_rooms[:5]:  # Показываем первые 5 комнат
        creator_name = room.players[room.creator_id].username or f"Игрок {room.creator_id}"
        players_count = len(room.players)
        keyboard.append([InlineKeyboardButton(
            f"Комната {room_id} ({players_count}/{room.max_players}) - {creator_name}",
            callback_data=f'join_room_{room_id}'
        )])
    
    if not available_rooms:
        keyboard.append([InlineKeyboardButton("❌ Нет доступных комнат", callback_data='none')])
    
    keyboard.append([InlineKeyboardButton("🔄 Обновить список", callback_data='refresh_rooms')])
    keyboard.append([InlineKeyboardButton("🔙 Главное меню", callback_data='back_to_main')])
    
    return InlineKeyboardMarkup(keyboard)

# Функции-обработчики
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик команды /start"""
    user = update.effective_user
    
    # Приветственное сообщение
    welcome_text = f"""
    👋 Привет, {user.first_name}!

    🚚 Добро пожаловать в игру "Доставка заказов"!

    📌 Возможности бота:
    • 🎮 Создание и присоединение к игровым комнатам
    • 📦 Выбор заказов (1-3 заказа за раз)
    • 📊 Отслеживание статистики
    • 📝 Создание заметок с адресами
    • 👥 Соревнование с другими игроками
    • ⏰ Ежечасная статистика и сравнение

    Выберите действие из меню ниже:
    """
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=get_main_menu_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )
    
    return States.MAIN_MENU.value

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Главное меню"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🏠 *Главное меню*\n\nВыберите действие:",
        reply_markup=get_main_menu_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )
    
    return States.MAIN_MENU.value

async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало игры - создание комнаты"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Проверяем, не находится ли пользователь уже в комнате
    existing_room = db.get_user_room(user_id)
    if existing_room:
        if existing_room.status == "waiting":
            await query.edit_message_text(
                f"⚠️ Вы уже находитесь в комнате *{existing_room.room_id}*\n\n"
                f"Ожидаем игроков...",
                reply_markup=get_game_room_keyboard(existing_room.room_id),
                parse_mode=ParseMode.MARKDOWN
            )
            return States.GAME_ROOM.value
        elif existing_room.status == "active":
            await query.edit_message_text(
                f"🎮 Вы уже в игре в комнате *{existing_room.room_id}*!\n\n"
                f"Игра уже началась. Выберите заказы или посмотрите статистику.",
                reply_markup=get_game_room_keyboard(existing_room.room_id),
                parse_mode=ParseMode.MARKDOWN
            )
            return States.GAME_ROOM.value
    
    # Создаем новую комнату
    room_id = db.create_game_room(user_id)
    room = db.game_rooms[room_id]
    
    # Обновляем имя пользователя
    if query.from_user.username:
        room.players[user_id].username = query.from_user.username
    else:
        room.players[user_id].username = query.from_user.first_name
    
    db.save_data()
    
    await query.edit_message_text(
        f"🎮 *Игровая комната создана!*\n\n"
        f"🔢 ID комнаты: `{room_id}`\n"
        f"👤 Игроков: {len(room.players)}/{room.max_players}\n"
        f"👑 Создатель: Вы\n\n"
        f"📋 *Инструкция:*\n"
        f"1. Поделитесь ID комнаты с другом\n"
        f"2. Ожидайте присоединения второго игрока\n"
        f"3. Начните игру, когда все будут готовы\n\n"
        f"Чтобы начать игру сразу, нажмите *'Выбрать заказы'*",
        reply_markup=get_game_room_keyboard(room_id),
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Запускаем таймер ожидания игроков
    context.job_queue.run_once(
        check_room_players,
        when=300,  # 5 минут
        data={'room_id': room_id, 'user_id': user_id},
        name=f"room_check_{room_id}"
    )
    
    return States.GAME_ROOM.value

async def join_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Присоединение к игре"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "👥 *Присоединение к игре*\n\n"
        "Выберите комнату из списка доступных:",
        reply_markup=get_join_game_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )
    
    return States.JOIN_GAME.value

async def join_room(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Присоединение к конкретной комнате"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data.split('_')
    
    if len(data) < 3:
        await query.edit_message_text(
            "❌ Ошибка: неверный ID комнаты",
            reply_markup=get_back_keyboard()
        )
        return States.JOIN_GAME.value
    
    room_id = data[2]
    
    if room_id not in db.game_rooms:
        await query.edit_message_text(
            "❌ Комната не найдена или уже закрыта",
            reply_markup=get_back_keyboard()
        )
        return States.JOIN_GAME.value
    
    room = db.game_rooms[room_id]
    
    # Проверяем, не находится ли пользователь уже в комнате
    if user_id in room.players:
        await query.edit_message_text(
            f"ℹ️ Вы уже в этой комнате!\n\n"
            f"ID комнаты: `{room_id}`",
            reply_markup=get_game_room_keyboard(room_id),
            parse_mode=ParseMode.MARKDOWN
        )
        return States.GAME_ROOM.value
    
    # Проверяем, есть ли места
    if len(room.players) >= room.max_players:
        await query.edit_message_text(
            "❌ В комнате нет свободных мест",
            reply_markup=get_back_keyboard()
        )
        return States.JOIN_GAME.value
    
    # Добавляем игрока
    new_player = Player(user_id)
    if query.from_user.username:
        new_player.username = query.from_user.username
    else:
        new_player.username = query.from_user.first_name
    
    if not room.add_player(new_player):
        await query.edit_message_text(
            "❌ Не удалось присоединиться к комнате",
            reply_markup=get_back_keyboard()
        )
        return States.JOIN_GAME.value
    
    db.save_data()
    
    # Оповещаем создателя комнаты
    try:
        await context.bot.send_message(
            chat_id=room.creator_id,
            text=f"🎉 *Новый игрок присоединился!*\n\n"
                 f"👤 Игрок: {new_player.username}\n"
                 f"🔢 Теперь игроков: {len(room.players)}/{room.max_players}\n\n"
                 f"ID комнаты: `{room_id}`",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Error notifying room creator: {e}")
    
    await query.edit_message_text(
        f"✅ *Вы присоединились к комнате!*\n\n"
        f"🔢 ID комнаты: `{room_id}`\n"
        f"👤 Игроков: {len(room.players)}/{room.max_players}\n"
        f"👑 Создатель: {room.players[room.creator_id].username}\n\n"
        f"Ожидайте начала игры или выберите 'Выбрать заказы' для старта",
        reply_markup=get_game_room_keyboard(room_id),
        parse_mode=ParseMode.MARKDOWN
    )
    
    return States.GAME_ROOM.value

async def select_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выбор заказов"""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split('_')
    room_id = data[2]
    
    if room_id not in db.game_rooms:
        await query.edit_message_text(
            "❌ Комната не найдена",
            reply_markup=get_back_keyboard()
        )
        return States.MAIN_MENU.value
    
    room = db.game_rooms[room_id]
    user_id = query.from_user.id
    
    if user_id not in room.players:
        await query.edit_message_text(
            "❌ Вы не участник этой комнаты",
            reply_markup=get_back_keyboard()
        )
        return States.MAIN_MENU.value
    
    # Если игра еще не начата, начинаем её
    if room.status == "waiting":
        room.start_game()
        db.save_data()
        
        # Оповещаем всех игроков
        for player_id in room.players:
            if player_id != user_id:
                try:
                    await context.bot.send_message(
                        chat_id=player_id,
                        text=f"🎮 *Игра началась!*\n\n"
                             f"Игрок {room.players[user_id].username} начал игру.\n"
                             f"ID комнаты: `{room_id}`\n\n"
                             f"Выберите 'Выбрать заказы' в меню комнаты",
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception as e:
                    logger.error(f"Error notifying player: {e}")
    
    # Генерируем заказы, если их нет
    if not room.current_orders:
        room.generate_orders()
        db.save_data()
    
    orders_text = "📦 *Доступные заказы:*\n\n"
    for i, order in enumerate(room.current_orders, 1):
        orders_text += (
            f"*Заказ #{i}:*\n"
            f"📍 Адрес: {order['address']}\n"
            f"⚖️ Вес: {order['weight']} кг\n"
            f"💰 Стоимость: {order['price']} ₽\n"
            f"⏱️ Лимит времени: {order['time_limit']} мин\n\n"
        )
    
    await query.edit_message_text(
        f"{orders_text}\n"
        f"Выберите заказ для доставки (можно взять до 3 заказов):",
        reply_markup=get_orders_selection_keyboard(room.current_orders, room_id),
        parse_mode=ParseMode.MARKDOWN
    )
    
    return States.SELECT_ORDERS.value

async def take_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Взять заказ"""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split('_')
    if len(data) < 4:
        await query.edit_message_text(
            "❌ Ошибка при выборе заказа",
            reply_markup=get_back_keyboard()
        )
        return States.MAIN_MENU.value
    
    room_id = data[2]
    order_id = data[3]
    
    if room_id not in db.game_rooms:
        await query.edit_message_text(
            "❌ Комната не найдена",
            reply_markup=get_back_keyboard()
        )
        return States.MAIN_MENU.value
    
    room = db.game_rooms[room_id]
    user_id = query.from_user.id
    
    if user_id not in room.players:
        await query.edit_message_text(
            "❌ Вы не участник этой комнаты",
            reply_markup=get_back_keyboard()
        )
        return States.MAIN_MENU.value
    
    # Находим заказ
    order = None
    for o in room.current_orders:
        if o['id'] == order_id:
            order = o
            break
    
    if not order:
        await query.edit_message_text(
            "❌ Заказ не найден",
            reply_markup=get_back_keyboard()
        )
        return States.SELECT_ORDERS.value
    
    player = room.players[user_id]
    
    # Обновляем статистику
    player.orders_taken += 1
    player.total_orders += 1
    player.last_activity = datetime.now()
    
    # Обновляем часовую статистику
    room.update_hourly_stats(user_id)
    
    # Удаляем заказ из доступных
    room.current_orders = [o for o in room.current_orders if o['id'] != order_id]
    
    db.save_data()
    
    # Оповещаем других игроков
    for player_id, other_player in room.players.items():
        if player_id != user_id:
            try:
                await context.bot.send_message(
                    chat_id=player_id,
                    text=f"📦 *Игрок {player.username} взял заказ!*\n\n"
                         f"📍 Адрес: {order['address']}\n"
                         f"💰 Стоимость: {order['price']} ₽\n\n"
                         f"📊 Статистика {player.username}:\n"
                         f"• Заказов сегодня: {player.orders_taken}\n"
                         f"• Всего заказов: {player.total_orders}\n\n"
                         f"🏃 *Ваша очередь действовать!*",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.error(f"Error notifying player: {e}")
    
    await query.edit_message_text(
        f"✅ *Вы успешно взяли заказ!*\n\n"
        f"📦 Детали заказа:\n"
        f"📍 Адрес: {order['address']}\n"
        f"⚖️ Вес: {order['weight']} кг\n"
        f"💰 Стоимость: {order['price']} ₽\n"
        f"⏱️ Лимит времени: {order['time_limit']} мин\n\n"
        f"📊 *Ваша статистика:*\n"
        f"• Заказов в этой игре: {player.orders_taken}\n"
        f"• Всего заказов: {player.total_orders}\n\n"
        f"Вы можете взять еще заказов или вернуться в меню.",
        reply_markup=get_orders_selection_keyboard(room.current_orders, room_id),
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Проверяем, нужно ли генерировать новые заказы
    if len(room.current_orders) == 0:
        room.generate_orders()
        db.save_data()
    
    # Запускаем задачу отправки статистики (если еще не запущена)
    if not room.stats_sent_at or (datetime.now() - room.stats_sent_at).seconds > 3600:
        context.job_queue.run_once(
            send_hourly_stats,
            when=3600,  # 1 час
            data={'room_id': room_id},
            name=f"stats_{room_id}"
        )
        room.stats_sent_at = datetime.now()
        db.save_data()
    
    return States.SELECT_ORDERS.value

async def view_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Просмотр статистики"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Получаем комнату пользователя
    room = db.get_user_room(user_id)
    
    if room and user_id in room.players:
        player = room.players[user_id]
        
        # Получаем лидерборд
        leaderboard = room.get_leaderboard()
        
        leaderboard_text = "🏆 *Текущий лидерборд:*\n\n"
        for i, (name, orders) in enumerate(leaderboard, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            leaderboard_text += f"{medal} {name}: {orders} заказов\n"
        
        stats_text = (
            f"📊 *Ваша статистика:*\n\n"
            f"👤 Имя: {player.username}\n"
            f"📦 Заказов в этой игре: {player.orders_taken}\n"
            f"📈 Всего заказов: {player.total_orders}\n"
            f"⏰ В игре с: {player.joined_at.strftime('%d.%m.%Y %H:%M')}\n\n"
            f"{leaderboard_text}\n"
        )
    else:
        stats_text = (
            "📊 *Ваша статистика:*\n\n"
            "Вы пока не участвовали в играх.\n"
            "Присоединитесь к игре, чтобы начать собирать статистику!"
        )
    
    await query.edit_message_text(
        stats_text,
        reply_markup=get_stats_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )
    
    return States.VIEW_STATS.value

async def hourly_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Часовая статистика"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    room = db.get_user_room(user_id)
    
    if not room or user_id not in room.players:
        await query.edit_message_text(
            "❌ Вы не в игре",
            reply_markup=get_back_keyboard()
        )
        return States.VIEW_STATS.value
    
    player = room.players[user_id]
    
    # Получаем статистику всех игроков за последний час
    current_hour = datetime.now().strftime("%Y-%m-%d %H:00")
    hourly_stats_text = f"📈 *Статистика за текущий час ({current_hour}):*\n\n"
    
    for player_id, p in room.players.items():
        if p != player:  # Пропускаем текущего игрока
            player_hourly = p.hourly_stats.get(current_hour, 0)
            hourly_stats_text += f"👤 {p.username}: {player_hourly} заказов\n"
    
    # Сравниваем с текущим игроком
    my_hourly = player.hourly_stats.get(current_hour, 0)
    
    # Находим лидера часа
    hourly_leader = None
    max_hourly = 0
    
    for p in room.players.values():
        player_hourly = p.hourly_stats.get(current_hour, 0)
        if player_hourly > max_hourly:
            max_hourly = player_hourly
            hourly_leader = p
    
    comparison_text = ""
    if hourly_leader and hourly_leader.user_id != user_id:
        difference = max_hourly - my_hourly
        if difference > 0:
            comparison_text = (
                f"\n⚠️ *Сравнение с лидером:*\n"
                f"🏆 Лидер: {hourly_leader.username} ({max_hourly} заказов)\n"
                f"📊 Вы отстаете на: {difference} заказов\n"
                f"💪 Вам нужно взять еще {difference + 1} заказов, чтобы обогнать!"
            )
        else:
            comparison_text = "\n🎉 *Вы лидер в этом часе!* Продолжайте в том же духе!"
    elif hourly_leader and hourly_leader.user_id == user_id:
        comparison_text = "\n🥇 *Вы лидируете в этом часе!* Так держать!"
    
    await query.edit_message_text(
        f"{hourly_stats_text}\n"
        f"📊 *Ваши заказы в этом часе:* {my_hourly}\n"
        f"{comparison_text}\n\n"
        f"Статистика обновляется каждый час автоматически.",
        reply_markup=get_stats_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )
    
    return States.VIEW_STATS.value

async def view_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Просмотр заметок"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    room = db.get_user_room(user_id)
    
    notes = []
    if room and user_id in room.players:
        notes = room.players[user_id].notes
    
    notes_text = "📝 *Ваши заметки:*\n\n"
    
    if notes:
        for i, note in enumerate(notes[:10], 1):
            notes_text += f"{i}. {note}\n"
        
        if len(notes) > 10:
            notes_text += f"\n... и еще {len(notes) - 10} заметок"
    else:
        notes_text += "У вас пока нет заметок.\nДобавьте первую заметку с помощью кнопки ниже."
    
    await query.edit_message_text(
        notes_text,
        reply_markup=get_notes_keyboard(notes),
        parse_mode=ParseMode.MARKDOWN
    )
    
    return States.VIEW_NOTES.value

async def add_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Добавление заметки"""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split('_')
    room_id = data[2] if len(data) > 2 else None
    
    await query.edit_message_text(
        "📝 *Добавление заметки*\n\n"
        "Введите текст заметки (адрес или другую информацию):\n\n"
        "Например: 📍 ул. Примерная, 123, кв. 45\n"
        "Или: 📦 Забрать посылку у консьержа\n\n"
        "Нажмите /cancel для отмены",
        reply_markup=get_back_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Сохраняем room_id в контексте
    if room_id:
        context.user_data['room_id'] = room_id
    
    return States.ADD_NOTE.value

async def save_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохранение заметки"""
    user_id = update.message.from_user.id
    note_text = update.message.text
    
    room_id = context.user_data.get('room_id')
    room = db.get_user_room(user_id)
    
    if not room:
        # Если пользователь не в комнате, сохраняем в сессии
        if 'notes' not in db.user_sessions.get(user_id, {}):
            db.user_sessions[user_id] = {'notes': []}
        db.user_sessions[user_id]['notes'].append(note_text)
        db.save_data()
        
        await update.message.reply_text(
            f"✅ Заметка сохранена!\n\n"
            f"📝 {note_text}\n\n"
            f"Всего заметок: {len(db.user_sessions[user_id]['notes'])}",
            reply_markup=get_main_menu_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
        
        return States.MAIN_MENU.value
    
    # Сохраняем заметку в профиле игрока
    if user_id in room.players:
        room.players[user_id].notes.append(note_text)
        db.save_data()
        
        await update.message.reply_text(
            f"✅ Заметка сохранена!\n\n"
            f"📝 {note_text}\n\n"
            f"Всего заметок: {len(room.players[user_id].notes)}",
            reply_markup=get_game_room_keyboard(room.room_id),
            parse_mode=ParseMode.MARKDOWN
        )
        
        return States.GAME_ROOM.value
    
    await update.message.reply_text(
        "❌ Ошибка при сохранении заметки",
        reply_markup=get_main_menu_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )
    
    return States.MAIN_MENU.value

async def back_to_room(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Возврат в комнату"""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split('_')
    room_id = data[3] if len(data) > 3 else None
    
    if not room_id or room_id not in db.game_rooms:
        await query.edit_message_text(
            "❌ Комната не найдена",
            reply_markup=get_main_menu_keyboard()
        )
        return States.MAIN_MENU.value
    
    room = db.game_rooms[room_id]
    user_id = query.from_user.id
    
    if user_id not in room.players:
        await query.edit_message_text(
            "❌ Вы не участник этой комнаты",
            reply_markup=get_main_menu_keyboard()
        )
        return States.MAIN_MENU.value
    
    room_status = "🟢 Активна" if room.status == "active" else "🟡 Ожидание"
    
    await query.edit_message_text(
        f"🎮 *Игровая комната*\n\n"
        f"🔢 ID: `{room_id}`\n"
        f"📊 Статус: {room_status}\n"
        f"👥 Игроков: {len(room.players)}/{room.max_players}\n"
        f"⏰ Время до конца: {((room.end_time - datetime.now()).seconds // 60) if room.end_time else 'Не начата'} мин\n\n"
        f"Выберите действие:",
        reply_markup=get_game_room_keyboard(room_id),
        parse_mode=ParseMode.MARKDOWN
    )
    
    return States.GAME_ROOM.value

async def leave_room(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выход из комнаты"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    room = db.get_user_room(user_id)
    
    if not room:
        await query.edit_message_text(
            "❌ Вы не находитесь в комнате",
            reply_markup=get_main_menu_keyboard()
        )
        return States.MAIN_MENU.value
    
    room_id = room.room_id
    player_name = room.players[user_id].username
    
    # Удаляем игрока из комнаты
    room.remove_player(user_id)
    
    # Если комната пуста, удаляем её
    if len(room.players) == 0:
        del db.game_rooms[room_id]
    
    db.save_data()
    
    # Оповещаем других игроков
    for player_id in room.players:
        try:
            await context.bot.send_message(
                chat_id=player_id,
                text=f"👋 *Игрок {player_name} покинул комнату*\n\n"
                     f"Осталось игроков: {len(room.players)}/{room.max_players}\n"
                     f"ID комнаты: `{room_id}`",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Error notifying players: {e}")
    
    await query.edit_message_text(
        f"🚪 *Вы вышли из комнаты*\n\n"
        f"🔢 ID комнаты: `{room_id}`\n"
        f"👤 Игроков осталось: {len(room.players)}\n\n"
        f"Вы можете создать новую игру или присоединиться к существующей.",
        reply_markup=get_main_menu_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )
    
    return States.MAIN_MENU.value

async def refresh_rooms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обновление списка комнат"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "👥 *Присоединение к игре*\n\n"
        "Выберите комнату из списка доступных:",
        reply_markup=get_join_game_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )
    
    return States.JOIN_GAME.value

async def refresh_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обновление списка заказов"""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split('_')
    room_id = data[2]
    
    if room_id not in db.game_rooms:
        await query.edit_message_text(
            "❌ Комната не найдена",
            reply_markup=get_back_keyboard()
        )
        return States.MAIN_MENU.value
    
    room = db.game_rooms[room_id]
    
    # Генерируем новые заказы
    room.generate_orders()
    db.save_data()
    
    orders_text = "🔄 *Заказы обновлены!*\n\n📦 *Доступные заказы:*\n\n"
    for i, order in enumerate(room.current_orders, 1):
        orders_text += (
            f"*Заказ #{i}:*\n"
            f"📍 Адрес: {order['address']}\n"
            f"⚖️ Вес: {order['weight']} кг\n"
            f"💰 Стоимость: {order['price']} ₽\n"
            f"⏱️ Лимит времени: {order['time_limit']} мин\n\n"
        )
    
    await query.edit_message_text(
        f"{orders_text}\n"
        f"Выберите заказ для доставки (можно взять до 3 заказов):",
        reply_markup=get_orders_selection_keyboard(room.current_orders, room_id),
        parse_mode=ParseMode.MARKDOWN
    )
    
    return States.SELECT_ORDERS.value

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Команда помощи"""
    query = update.callback_query
    await query.answer()
    
    help_text = """
    🆘 *Помощь по боту*

    *🎮 Как начать игру:*
    1. Нажмите "Начать игру" для создания комнаты
    2. Поделитесь ID комнаты с другом
    3. Начните выбирать заказы

    *➕ Как присоединиться:*
    1. Нажмите "Присоединиться к игре"
    2. Выберите доступную комнату
    3. Начните играть

    *📦 Система заказов:*
    • В боксе появляется 1-3 случайных заказа
    • Вы можете взять любой заказ
    • После взятия заказа появляются новые
    • Соперник видит ваши действия

    *📊 Статистика:*
    • Часовая статистика обновляется автоматически
    • Видно, сколько заказов взял соперник
    • Рекомендации по обгону соперника
    • Общая статистика за все время

    *📝 Заметки:*
    • Добавляйте адреса и другую информацию
    • Просматривайте список заметок
    • Заметки сохраняются даже после выхода

    *⏰ Автоматизация:*
    • Бот работает 24/7 на сервере
    • Автоматические уведомления
    • Ежечасная статистика
    • Очистка неактивных комнат

    *🔧 Команды:*
    /start - Главное меню
    /help - Эта справка
    /stats - Ваша статистика
    /notes - Ваши заметки

    *🔄 Обновления:*
    Бот постоянно улучшается.
    Предложения отправляйте разработчику.
    """
    
    await query.edit_message_text(
        help_text,
        reply_markup=get_main_menu_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )
    
    return States.MAIN_MENU.value

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена текущего действия"""
    user = update.effective_user
    
    await update.message.reply_text(
        "❌ Действие отменено.",
        reply_markup=get_main_menu_keyboard()
    )
    
    return States.MAIN_MENU.value

# Фоновые задачи
async def check_room_players(context: ContextTypes.DEFAULT_TYPE):
    """Проверка комнаты на наличие игроков"""
    job = context.job
    room_id = job.data['room_id']
    user_id = job.data['user_id']
    
    if room_id not in db.game_rooms:
        return
    
    room = db.game_rooms[room_id]
    
    # Если в комнате только один игрок и игра не начата
    if len(room.players) == 1 and room.status == "waiting":
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"⏰ *Напоминание о комнате*\n\n"
                     f"Вы все еще один в комнате `{room_id}`.\n"
                     f"Пригласите друзей или начните игру в одиночку!\n\n"
                     f"Комната будет автоматически закрыта через 24 часа бездействия.",
                reply_markup=get_game_room_keyboard(room_id),
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Error sending reminder: {e}")

async def send_hourly_stats(context: ContextTypes.DEFAULT_TYPE):
    """Отправка ежечасной статистики"""
    job = context.job
    room_id = job.data['room_id']
    
    if room_id not in db.game_rooms:
        return
    
    room = db.game_rooms[room_id]
    
    # Обновляем время отправки статистики
    room.stats_sent_at = datetime.now()
    db.save_data()
    
    # Формируем статистику
    current_hour = datetime.now().strftime("%Y-%m-%d %H:00")
    leaderboard = room.get_leaderboard()
    
    stats_text = f"⏰ *Ежечасная статистика ({current_hour})*\n\n🏆 *Лидерборд:*\n\n"
    
    for i, (name, orders) in enumerate(leaderboard, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        stats_text += f"{medal} {name}: {orders} заказов\n"
    
    stats_text += "\n💪 *Продолжайте в том же духе!*\n"
    stats_text += "Следующая статистика будет через час."
    
    # Отправляем всем игрокам
    for player_id in room.players:
        try:
            # Добавляем персональную рекомендацию
            player = room.players[player_id]
            player_position = next(
                (i for i, (name, _) in enumerate(leaderboard, 1) if name == player.username),
                None
            )
            
            personal_advice = ""
            if player_position and player_position > 1:
                leader_orders = leaderboard[0][1]
                difference = leader_orders - player.orders_taken
                personal_advice = (
                    f"\n📊 *Ваша позиция:* #{player_position}\n"
                    f"📈 До лидера: {difference} заказов\n"
                    f"🎯 Рекомендация: возьмите еще {difference + 1} заказов"
                )
            elif player_position == 1:
                second_orders = leaderboard[1][1] if len(leaderboard) > 1 else 0
                difference = player.orders_taken - second_orders
                personal_advice = (
                    f"\n🥇 *Вы лидируете!*\n"
                    f"📈 Отрыв: {difference} заказов\n"
                    f"💪 Продолжайте лидировать!"
                )
            
            await context.bot.send_message(
                chat_id=player_id,
                text=f"{stats_text}{personal_advice}",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Error sending hourly stats to {player_id}: {e}")

async def cleanup_job(context: ContextTypes.DEFAULT_TYPE):
    """Очистка неактивных комнат"""
    db.cleanup_inactive_rooms()
    logger.info("Cleanup job executed")

# Основная функция
def main() -> None:
    """Запуск бота"""
    # Токен бота (замените на свой)
    TOKEN = "YOUR_BOT_TOKEN_HERE"
    
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()
    
    # Обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", view_stats))
    application.add_handler(CommandHandler("notes", view_notes))
    
    # Conversation Handler для основного потока
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            States.MAIN_MENU.value: [
                CallbackQueryHandler(start_game, pattern='^start_game$'),
                CallbackQueryHandler(join_game, pattern='^join_game$'),
                CallbackQueryHandler(view_stats, pattern='^view_stats$'),
                CallbackQueryHandler(view_notes, pattern='^view_notes$'),
                CallbackQueryHandler(help_command, pattern='^help$'),
                CallbackQueryHandler(main_menu, pattern='^back_to_main$'),
            ],
            States.JOIN_GAME.value: [
                CallbackQueryHandler(join_room, pattern='^join_room_'),
                CallbackQueryHandler(refresh_rooms, pattern='^refresh_rooms$'),
                CallbackQueryHandler(main_menu, pattern='^back_to_main$'),
            ],
            States.GAME_ROOM.value: [
                CallbackQueryHandler(select_orders, pattern='^select_orders_'),
                CallbackQueryHandler(add_note, pattern='^add_note_'),
                CallbackQueryHandler(leave_room, pattern='^leave_room$'),
                CallbackQueryHandler(back_to_room, pattern='^back_to_room_'),
                CallbackQueryHandler(main_menu, pattern='^back_to_main$'),
            ],
            States.SELECT_ORDERS.value: [
                CallbackQueryHandler(take_order, pattern='^take_order_'),
                CallbackQueryHandler(refresh_orders, pattern='^refresh_orders_'),
                CallbackQueryHandler(back_to_room, pattern='^back_to_room_'),
            ],
            States.VIEW_STATS.value: [
                CallbackQueryHandler(hourly_stats, pattern='^hourly_stats$'),
                CallbackQueryHandler(view_stats, pattern='^total_stats$'),
                CallbackQueryHandler(view_stats, pattern='^leaders$'),
                CallbackQueryHandler(main_menu, pattern='^back_to_main$'),
            ],
            States.VIEW_NOTES.value: [
                CallbackQueryHandler(add_note, pattern='^add_new_note$'),
                CallbackQueryHandler(main_menu, pattern='^back_to_main$'),
            ],
            States.ADD_NOTE.value: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_note),
                CommandHandler("cancel", cancel),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    application.add_handler(conv_handler)
    
    # Обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Запускаем фоновые задачи
    job_queue = application.job_queue
    
    # Очистка неактивных комнат каждые 6 часов
    job_queue.run_repeating(cleanup_job, interval=21600, first=10)
    
    # Запускаем бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Exception while handling an update: {context.error}")
    
    try:
        if update and update.effective_chat:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Произошла ошибка. Пожалуйста, попробуйте снова или вернитесь в главное меню.",
                reply_markup=get_main_menu_keyboard()
            )
    except Exception as e:
        logger.error(f"Error in error handler: {e}")

if __name__ == "__main__":
    print("🚀 Запуск бота...")
    print("📊 База данных загружена")
    print("⏰ Фоновые задачи инициализированы")
    print("🤖 Бот готов к работе!")
    
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Завершение работы бота...")
        db.save_data()
        print("💾 Данные сохранены")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        db.save_data()
