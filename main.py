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
    photos = State()
    confirm = State()

# ================== KEYBOARDS ==================

main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
main_kb.add("📢 Опубликовать объявление")
main_kb.add("📖 Помощь", "📞 Связь с владельцем")
main_kb.add("👮 Модераторы")

photo_kb = ReplyKeyboardMarkup(resize_keyboard=True)
photo_kb.add("✅ ГОТОВО")

confirm_kb = InlineKeyboardMarkup().add(
    InlineKeyboardButton("✅ Подтвердить", callback_data="confirm"),
    InlineKeyboardButton("❌ Отменить", callback_data="cancel")
)

def moderation_kb(ad_id: int):
    return InlineKeyboardMarkup().add(
        InlineKeyboardButton("✅ Одобрить", callback_data=f"approve:{ad_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject:{ad_id}")
    )

# ================== START ==================

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    save_user(message.from_user.id)
    await message.answer(
        "👋 Добро пожаловать!",
        reply_markup=main_kb
    )

# ================== INFO ==================

@dp.message_handler(text="📖 Помощь")
async def help_msg(message: types.Message):
    await message.answer(
        "📌 <b>Как подать объявление</b>\n\n"
        "1️⃣ Нажмите «Опубликовать объявление»\n"
        "2️⃣ Напишите текст\n"
        "3️⃣ Добавьте фото (до 5)\n"
        "4️⃣ Нажмите «Готово»\n"
        "5️⃣ Подтвердите",
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
        "🛡 @creatorr13\n"
        "🛡 @krasnov_hub",
        reply_markup=main_kb
    )

# ================== SUBMIT ==================

@dp.message_handler(text="📢 Опубликовать объявление")
async def start_ad(message: types.Message):
    save_user(message.from_user.id)

    uid = message.from_user.id
    now = time.time()

    if uid in last_post_time and now - last_post_time[uid] < ANTISPAM_SECONDS:
        await message.answer("⏳ Подождите перед следующей подачей", reply_markup=main_kb)
        return

    await message.answer(
        "✍️ <b>Подача объявления</b>\n\n"
        "Отправьте <b>текст объявления</b> одним сообщением.\n\n"
        "⚠️ <b>ФОТО ДОБАВЛЯЮТСЯ НА СЛЕДУЮЩЕМ ШАГЕ!</b>",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await AdForm.text.set()

@dp.message_handler(state=AdForm.text)
async def get_text(message: types.Message, state: FSMContext):
    await state.update_data(text=message.text, photos=[])
    await message.answer(
        "📸 Отправьте до 5 фото.\n"
        "После загрузки нажмите <b>ГОТОВО</b>.",
        reply_markup=photo_kb
    )
    await AdForm.photos.set()

@dp.message_handler(state=AdForm.photos, content_types=types.ContentTypes.PHOTO)
async def get_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photos = data["photos"]

    if len(photos) < MAX_PHOTOS:
        photos.append(message.photo[-1].file_id)
        await state.update_data(photos=photos)

@dp.message_handler(state=AdForm.photos, text="✅ ГОТОВО")
async def finish_photos(message: types.Message, state: FSMContext):
    data = await state.get_data()

    await message.answer("🔍 <b>Предпросмотр</b>")

    if data["photos"]:
        media = [InputMediaPhoto(data["photos"][0], caption=data["text"])]
        for p in data["photos"][1:]:
            media.append(InputMediaPhoto(p))
        await bot.send_media_group(message.chat.id, media)
    else:
        await message.answer(data["text"])

    await message.answer("Подтвердите:", reply_markup=confirm_kb)
    await AdForm.confirm.set()

# ================== CONFIRM ==================

@dp.callback_query_handler(text="confirm", state=AdForm.confirm)
async def confirm(call: types.CallbackQuery, state: FSMContext):
    global ad_counter
    ad_counter += 1
    ad_id = ad_counter

    data = await state.get_data()
    user = call.from_user

    pending_ads[ad_id] = {
        "user": user,
        "text": data["text"],
        "photos": data["photos"]
    }

    caption = f"🆕 <b>Объявление №{ad_id}</b>\n\n{data['text']}"

    for mid in MODERATORS:
        if data["photos"]:
            media = [InputMediaPhoto(data["photos"][0], caption=caption)]
            for p in data["photos"][1:]:
                media.append(InputMediaPhoto(p))
            await bot.send_media_group(mid, media)
            await bot.send_message(mid, "⬆️ Модерация", reply_markup=moderation_kb(ad_id))
        else:
            await bot.send_message(mid, caption, reply_markup=moderation_kb(ad_id))

    last_post_time[user.id] = time.time()
    await state.finish()
    await call.message.answer("✅ Отправлено на модерацию", reply_markup=main_kb)
    await call.answer()

@dp.callback_query_handler(text="cancel", state=AdForm.confirm)
async def cancel(call: types.CallbackQuery, state: FSMContext):
    await state.finish()
    await call.message.answer("❌ Отменено", reply_markup=main_kb)
    await call.answer()

# ================== MODERATION ==================

@dp.callback_query_handler(lambda c: c.data.startswith(("approve:", "reject:")))
async def moderate(call: types.CallbackQuery):
    if call.from_user.id not in MODERATORS:
        return

    action, ad_id = call.data.split(":")
    ad_id = int(ad_id)

    if ad_id in processed_ads:
        await call.answer("Уже обработано", show_alert=True)
        return

    ad = pending_ads[ad_id]
    processed_ads[ad_id] = True

    if action == "approve":
        if ad["photos"]:
            media = [InputMediaPhoto(ad["photos"][0], caption=ad["text"])]
            for p in ad["photos"][1:]:
                media.append(InputMediaPhoto(p))
            await bot.send_media_group(CHANNEL_ID, media)
        else:
            await bot.send_message(CHANNEL_ID, ad["text"])
        await bot.send_message(ad["user"].id, "✅ Объявление опубликовано")
    else:
        await bot.send_message(ad["user"].id, "❌ Объявление отклонено")

    await call.message.edit_reply_markup()
    await call.answer("Готово")

# ================== SERVICE ==================

@dp.message_handler(commands=["users"])
async def users_cmd(message: types.Message):
    if message.from_user.id == OWNER_ID:
        await message.answer(f"👥 Пользователей: {len(users)}")

@dp.message_handler(commands=["broadcast"])
async def broadcast(message: types.Message):
    if message.from_user.id != OWNER_ID:
        return

    text = message.get_args()
    if not text:
        await message.answer("❌ Напиши текст")
        return

    sent = 0
    for uid in users:
        try:
            await bot.send_message(uid, text)
            sent += 1
            await asyncio.sleep(0.05)
        except:
            pass

    await message.answer(f"✅ Отправлено: {sent}")

# ================== RUN ==================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
