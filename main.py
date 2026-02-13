import logging
import time
import asyncio
import os

from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto
)

# ================== НАСТРОЙКИ ==================

TOKEN = "8514017811:AAFKyBdlLjHTVlF1ql5Axe2WUZx2l9lgnFg"
CHANNEL_ID = "@blackrussia_85"
OWNER_ID = 724545647
OWNER_USERNAME = "@onesever"

MODERATORS = [
    724545647,
    7244927531,
    8390126598,
    6077303991,
    6621231808,
]

ANTISPAM_SECONDS = 2 * 60 * 60
MAX_PHOTOS = 5
USERS_FILE = "users.txt"

# ================== INIT ==================

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN, parse_mode="HTML")
dp = Dispatcher(bot, storage=MemoryStorage())

# ================== ПРОВЕРКА ПОДПИСКИ ==================

async def check_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

subscribe_kb = InlineKeyboardMarkup().add(
    InlineKeyboardButton(
        "📢 Подписаться",
        url=f"https://t.me/{CHANNEL_ID.replace('@', '')}"
    ),
    InlineKeyboardButton("✅ Я подписался", callback_data="check_sub")
)

# ================== USERS ==================

users = set()

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            for line in f:
                if line.strip().isdigit():
                    users.add(int(line.strip()))

def save_user(uid: int):
    if uid not in users:
        users.add(uid)
        with open(USERS_FILE, "a") as f:
            f.write(f"{uid}\n")

load_users()

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

# ================== KEYBOARDS ==================

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

def moderation_kb(ad_id):
    return InlineKeyboardMarkup().add(
        InlineKeyboardButton("✅ Одобрить", callback_data=f"approve:{ad_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject:{ad_id}")
    )

# ================== START ==================

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    save_user(message.from_user.id)

    if not await check_subscription(message.from_user.id):
        await message.answer(
            "❗ Для использования бота необходимо подписаться на канал.",
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
        await call.message.edit_text(
            "✅ Подписка подтверждена!\n\nТеперь можете пользоваться ботом."
        )
        await call.message.answer("Выберите действие:", reply_markup=main_kb)
    else:
        await call.answer("❌ Вы ещё не подписались", show_alert=True)

# ================== INFO ==================

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
        "🛡️ @MensClub4",
        reply_markup=main_kb
    )

# ================== SUBMIT ==================

@dp.message_handler(text="📢 Опубликовать объявление")
async def start_ad(message: types.Message):
    save_user(message.from_user.id)

    if not await check_subscription(message.from_user.id):
        await message.answer(
            "❗ Для подачи объявления нужно подписаться на канал.",
            reply_markup=subscribe_kb
        )
        return

    uid = message.from_user.id
    now = time.time()

    if uid in last_post_time:
        diff = int(now - last_post_time[uid])
        if diff < ANTISPAM_SECONDS:
            await message.answer(
                f"⏳ Подождите {ANTISPAM_SECONDS - diff}",
                reply_markup=main_kb
            )
            return

    await message.answer(
        "✍️ <b>Подача объявления</b>\n\n"
        "Отправьте <b>текст объявления</b> одним сообщением.",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await AdForm.text.set()

# ================== RUN ==================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
