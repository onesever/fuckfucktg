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
    7946280692,
    7244927531,
]

ANTISPAM_SECONDS = 2 * 60 * 60
MAX_PHOTOS = 5
USERS_FILE = "users.txt"

# ================== INIT ==================

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN, parse_mode="HTML")
dp = Dispatcher(bot, storage=MemoryStorage())

# ================== USERS ==================

users = set()

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            for line in f:
                if line.strip().isdigit():
                    users.add(int(line.strip()))

def save_user(user_id: int):
    if user_id not in users:
        users.add(user_id)
        with open(USERS_FILE, "a") as f:
            f.write(f"{user_id}\n")

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

def moderation_kb(ad_id: int):
    return InlineKeyboardMarkup().add(
        InlineKeyboardButton("✅ Одобрить", callback_data=f"approve:{ad_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject:{ad_id}")
    )

# ================== UTILS ==================

def format_time(sec: int) -> str:
    h = sec // 3600
    m = (sec % 3600) // 60
    return f"{h} ч {m} мин" if h else f"{m} мин"

# ================== START ==================

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    save_user(message.from_user.id)
    await message.answer(
        "👋 Добро пожаловать!\n\nВы можете подать объявление.",
        reply_markup=main_kb
    )

# ================== SUBMIT ==================

@dp.message_handler(text="📢 Опубликовать объявление")
async def start_ad(message: types.Message):
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
    await state.update_data(text=message.text, photos=[])
    await message.answer("📸 Хотите добавить фото?", reply_markup=ask_photo_kb)
    await AdForm.ask_photo.set()

@dp.message_handler(state=AdForm.ask_photo, text="➡️ Без фото")
async def no_photo(message: types.Message, state: FSMContext):
    await show_preview(message, state)

@dp.message_handler(state=AdForm.ask_photo, text="➕ Добавить фото")
async def add_photo(message: types.Message):
    await message.answer(
        "📸 Отправьте до 5 фото.\n\n"
        "⚠️ <b>НАЖМИТЕ «ГОТОВО», КОГДА ЗАКОНЧИТЕ</b>",
        reply_markup=photo_done_kb
    )
    await AdForm.photos.set()

@dp.message_handler(state=AdForm.photos, content_types=types.ContentTypes.PHOTO)
async def get_photos(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])

    if len(photos) < MAX_PHOTOS:
        photos.append(message.photo[-1].file_id)
        await state.update_data(photos=photos)

    if len(photos) == MAX_PHOTOS:
        await show_preview(message, state)

@dp.message_handler(state=AdForm.photos, text="✅ Готово")
async def photos_done(message: types.Message, state: FSMContext):
    await show_preview(message, state)

# ================== PREVIEW ==================

async def show_preview(message: types.Message, state: FSMContext):
    data = await state.get_data()

    await message.answer("🔍 <b>Предпросмотр</b>", reply_markup=types.ReplyKeyboardRemove())

    if data["photos"]:
        media = [InputMediaPhoto(data["photos"][0], caption=data["text"])]
        for p in data["photos"][1:]:
            media.append(InputMediaPhoto(p))
        await bot.send_media_group(message.chat.id, media)
    else:
        await message.answer(data["text"])

    await message.answer("Подтвердите:", reply_markup=confirm_kb)
    await AdForm.confirm.set()

# ================== RUN ==================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
