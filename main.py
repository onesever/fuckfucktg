import logging
import time
import asyncio
import os
import sqlite3

from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto
)

# ================== НАСТРОЙКИ ==================

TOKEN = "ТВОЙ_ТОКЕН"
CHANNEL_ID = "@blackrussia_85"

OWNER_ID = 724545647
OWNER_USERNAME = "@onesever"

MODERATORS = [
    724545647,
    7244927531,
    8390126598,
    6077303991,
    5743211958,
    6621231808,
]

ANTISPAM_SECONDS = 2 * 60 * 60
MAX_PHOTOS = 5

# ================== INIT ==================

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN, parse_mode="HTML")
dp = Dispatcher(bot, storage=MemoryStorage())

# ================== DATABASE (SQLite) ==================

conn = sqlite3.connect("database.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY
)
""")
conn.commit()

def save_user(uid: int):
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (uid,))
    conn.commit()

def get_users():
    cursor.execute("SELECT user_id FROM users")
    return [row[0] for row in cursor.fetchall()]

# ================== STORAGE ==================

last_post_time = {}
pending_ads = {}
processed_ads = {}
ad_counter = 0

# ================== FSM ==================

class AdForm(StatesGroup):
    text = State()
    ask_photo = State()
    photos = State()
    confirm = State()

# ================== КЛАВИАТУРЫ ==================

main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
main_kb.add("📢 Опубликовать объявление")
main_kb.add("📖 Помощь", "📞 Связь с владельцем")
main_kb.add("👮 Модераторы")

ask_photo_kb = ReplyKeyboardMarkup(resize_keyboard=True)
ask_photo_kb.add("➕ Добавить фото", "➡️ Без фото")

photo_done_kb = ReplyKeyboardMarkup(resize_keyboard=True)
photo_done_kb.add("✅ Готово")

confirm_kb = InlineKeyboardMarkup().add(
    InlineKeyboardButton("✅ Подтвердить", callback_data="confirm"),
    InlineKeyboardButton("❌ Отменить", callback_data="cancel")
)

subscribe_kb = InlineKeyboardMarkup().add(
    InlineKeyboardButton("📢 Подписаться", url=f"https://t.me/{CHANNEL_ID[1:]}"),
    InlineKeyboardButton("✅ Проверить подписку", callback_data="check_sub")
)

def moderation_kb(ad_id):
    return InlineKeyboardMarkup().add(
        InlineKeyboardButton("✅ Одобрить", callback_data=f"approve:{ad_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject:{ad_id}")
    )

# ================== УТИЛИТЫ ==================

def format_time(sec: int) -> str:
    hours = sec // 3600
    minutes = (sec % 3600) // 60

    if hours > 0 and minutes > 0:
        return f"{hours} ч {minutes} мин"
    elif hours > 0:
        return f"{hours} ч"
    else:
        return f"{minutes} мин"

async def check_subscription(user_id):
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

# ================== START ==================

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    save_user(message.from_user.id)

    if not await check_subscription(message.from_user.id):
        await message.answer(
            "❌ Для использования бота необходимо подписаться на канал.",
            reply_markup=subscribe_kb
        )
        return

    await message.answer(
        "👋 Добро пожаловать!\n\nВы можете подать объявление.",
        reply_markup=main_kb
    )

@dp.callback_query_handler(text="check_sub")
async def check_sub(call: types.CallbackQuery):
    if await check_subscription(call.from_user.id):
        await call.message.edit_text("✅ Подписка подтверждена!")
        await call.message.answer(
            "👋 Добро пожаловать!\n\nВы можете подать объявление.",
            reply_markup=main_kb
        )
    else:
        await call.answer("❌ Вы не подписаны!", show_alert=True)

# ================== ИНФО ==================

@dp.message_handler(text="📖 Помощь")
async def help_msg(message: types.Message):
    await message.answer(
        "📌 <b>Как подать объявление</b>\n\n"
        "1️⃣ Опубликовать объявление\n"
        "2️⃣ Написать текст\n"
        "3️⃣ Добавить фото (по желанию)\n"
        "4️⃣ Подтвердить\n\n"
        "⏳ 1 объявление раз в 2 часа",
        reply_markup=main_kb
    )

@dp.message_handler(text="📞 Связь с владельцем")
async def owner(message: types.Message):
    await message.answer(f"👑 Владелец: {OWNER_USERNAME}", reply_markup=main_kb)

@dp.message_handler(text="👮 Модераторы")
async def mods(message: types.Message):
    await message.answer(
        "👮 <b>Модераторы</b>\n\n"
        "👑 @onesever\n"
        "🛡️ @creatorr13\n"
        "🛡️ @wrezx\n"
        "🛡️ @qwixx_am\n"
        "🛡️ @Bob1na\n"
        "🛡️ @MensClub4",
        reply_markup=main_kb
    )

# ================== ПОДАЧА ==================

@dp.message_handler(text="📢 Опубликовать объявление")
async def start_ad(message: types.Message):

    if not await check_subscription(message.from_user.id):
        await message.answer(
            "❌ Для подачи объявления нужно подписаться на канал.",
            reply_markup=subscribe_kb
        )
        return

    save_user(message.from_user.id)

    uid = message.from_user.id
    now = time.time()

    if uid in last_post_time:
        diff = int(now - last_post_time[uid])
        if diff < ANTISPAM_SECONDS:
            await message.answer(
                f"⏳ Подождите {format_time(ANTISPAM_SECONDS - diff)}",
                reply_markup=main_kb
            )
            return

    await message.answer(
        "✍️ <b>Подача объявления</b>\n\n"
        "Отправьте <b>текст объявления</b> одним сообщением.\n\n"
        "📌 <b>Пример:</b>\n"
        "Продам дом в Бусаево\n"
        "Цена: 17кк\n"
        "Связь: @username\n\n"
        "⚠️ <b>ФОТО ДОБАВЛЯЮТСЯ НА СЛЕДУЮЩЕМ ШАГЕ!</b>",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await AdForm.text.set()

@dp.message_handler(state=AdForm.text, content_types=types.ContentTypes.TEXT)
async def get_text(message: types.Message, state: FSMContext):

    user = message.from_user
    text = message.text

    if not user.username:
        await message.answer(
            "❌ У вас не установлен username в Telegram.\n"
            "Установите его в настройках и попробуйте снова."
        )
        return

    if f"@{user.username}" not in text:
        await message.answer(
            "❌ В объявлении должен быть указан ВАШ username.\n\n"
            f"Добавьте строку вида:\n"
            f"Связь: @{user.username}"
        )
        return

    await state.update_data(text=text, photos=[])
    await message.answer("📸 Хотите добавить фото?", reply_markup=ask_photo_kb)
    await AdForm.ask_photo.set()

# ================== RUN ==================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
