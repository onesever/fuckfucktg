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
    7573908814,
    6621231808,
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
        "🛡️ @sqw1rtit\n"
        "🛡️ @MensClub4",
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
        "📸 Отправьте до 5 фото.\n"
        "После отправки всех фото нажмите «Готово».",
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

@dp.message_handler(state=AdForm.photos, text="✅ Готово")
async def photos_done(message: types.Message, state: FSMContext):
    await show_preview(message, state)

# ================== PREVIEW ==================

async def show_preview(message: types.Message, state: FSMContext):
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

    caption = (
        f"🆕 <b>Объявление №{ad_id}</b>\n"
        f"👤 {user.full_name} (@{user.username})\n"
        f"🆔 {user.id}\n\n"
        f"{data['text']}"
    )

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
    await call.message.answer("✅ Объявление отправлено на модерацию", reply_markup=main_kb)
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

    ad = pending_ads.get(ad_id)
    if not ad:
        return

    processed_ads[ad_id] = call.from_user.full_name

    if action == "approve":
        if ad["photos"]:
            media = [InputMediaPhoto(ad["photos"][0], caption=ad["text"])]
            for p in ad["photos"][1:]:
                media.append(InputMediaPhoto(p))
            await bot.send_media_group(CHANNEL_ID, media)
        else:
            await bot.send_message(CHANNEL_ID, ad["text"])
        await bot.send_message(ad["user"].id, f"✅ Объявление №{ad_id} опубликовано")
        status = "ОДОБРЕНО"
    else:
        await bot.send_message(ad["user"].id, f"❌ Объявление №{ad_id} отклонено")
        status = "ОТКЛОНЕНО"

    for mid in MODERATORS:
        await bot.send_message(
            mid,
            f"📌 Объявление №{ad_id} {status}\n"
            f"👮 {call.from_user.full_name}"
        )

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
        await message.answer("❌ Напиши текст после команды")
        return

    sent = 0
    for uid in list(users):
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
