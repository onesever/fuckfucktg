import logging
import json
import time
import asyncio

from aiogram import Bot, Dispatcher, executor, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto
)

# ================= НАСТРОЙКИ =================
TOKEN = "8514017811:AAEv62jJ8--g7sIUeTf6C9c54wvQNlUPTqE"

ADMIN_IDS = [724545647, 8390126598]
CHANNEL_ID = "@blackrussia_85"
CONTACT_ADMIN = "@onesever"

PENDING_FILE = "pending.json"
COUNTER_FILE = "counter.json"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
lock = asyncio.Lock()

# ================= FSM =================
class AdForm(StatesGroup):
    text = State()
    photos = State()

# ================= JSON =================
def load_json(file):
    try:
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_next_number():
    data = load_json(COUNTER_FILE)
    num = data.get("last", 0) + 1
    data["last"] = num
    save_json(COUNTER_FILE, data)
    return num

# ================= КЛАВИАТУРЫ =================
user_kb = ReplyKeyboardMarkup(resize_keyboard=True)
user_kb.add("📢 Опубликовать объявление")
user_kb.add("📖 Помощь", "📞 Связь с админом")

photo_kb = ReplyKeyboardMarkup(resize_keyboard=True)
photo_kb.add("📷 Добавить фото")
photo_kb.add("🚫 Без фото")

finish_kb = ReplyKeyboardMarkup(resize_keyboard=True)
finish_kb.add("✅ Готово")
finish_kb.add("🚫 Без фото")

# ================= START =================
@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer(
        "👋 Привет!\n\n"
        "Ты можешь подать объявление для публикации.",
        reply_markup=user_kb
    )

@dp.message_handler(text="📖 Помощь")
async def help_msg(message: types.Message):
    await message.answer(
        "📌 Как подать объявление:\n"
        "1️⃣ Напиши текст\n"
        "2️⃣ Добавь фото (по желанию)\n"
        "3️⃣ Отправь на модерацию"
    )

@dp.message_handler(text="📞 Связь с админом")
async def contact(message: types.Message):
    await message.answer(f"📞 Администратор: {CONTACT_ADMIN}")

# ================= ПОДАЧА =================
@dp.message_handler(text="📢 Опубликовать объявление")
async def start_ad(message: types.Message):
    await AdForm.text.set()
    await message.answer(
        "✏️ Напишите текст объявления",
        reply_markup=types.ReplyKeyboardRemove()
    )

@dp.message_handler(state=AdForm.text, content_types=types.ContentType.TEXT)
async def get_text(message: types.Message, state: FSMContext):
    await state.update_data(
        text=message.text,
        photos=[]
    )
    await AdForm.photos.set()
    await message.answer(
        "📸 Добавьте фото к объявлению\n"
        "Можно несколько\n"
        "Или нажмите «Без фото»",
        reply_markup=photo_kb
    )

@dp.message_handler(state=AdForm.photos, text="🚫 Без фото")
async def no_photo(message: types.Message, state: FSMContext):
    await send_to_moderation(message, state, with_photos=False)

@dp.message_handler(state=AdForm.photos, text="📷 Добавить фото")
async def ask_photo(message: types.Message):
    await message.answer(
        "📸 Отправляйте фото\n"
        "Когда закончите — нажмите «Готово»",
        reply_markup=finish_kb
    )

@dp.message_handler(state=AdForm.photos, content_types=types.ContentType.PHOTO)
async def collect_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    photos.append(message.photo[-1].file_id)
    await state.update_data(photos=photos)

@dp.message_handler(state=AdForm.photos, text="✅ Готово")
async def finish_photos(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("photos"):
        await message.answer("❌ Вы не добавили фото\nИли нажмите «Без фото»")
        return
    await send_to_moderation(message, state, with_photos=True)

# ================= ОТПРАВКА АДМИНАМ =================
async def send_to_moderation(message, state, with_photos: bool):
    data = await state.get_data()
    number = get_next_number()
    post_id = str(int(time.time() * 1000))

    user = message.from_user

    header = (
        f"🆕 Объявление №{number}\n"
        f"👤 {user.full_name}"
        f"{f' (@{user.username})' if user.username else ''}\n"
        f"🆔 ID: {user.id}"
    )

    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("✅ Одобрить", callback_data=f"approve:{post_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject:{post_id}")
    )

    pending = load_json(PENDING_FILE)
    pending[post_id] = {
        "number": number,
        "text": data["text"],
        "photos": data.get("photos", []),
        "from_id": user.id,
        "status": "pending"
    }
    save_json(PENDING_FILE, pending)

    for admin in ADMIN_IDS:
        await bot.send_message(admin, header)
        await bot.send_message(admin, f"📝 Текст:\n\n{data['text']}")

        if with_photos:
            media = [
                InputMediaPhoto(
                    media=pid,
                    caption=data["text"] if i == 0 else None
                )
                for i, pid in enumerate(data["photos"])
            ]
            await bot.send_media_group(admin, media)

        await bot.send_message(admin, "⬆️ Модерация", reply_markup=kb)

    await state.finish()
    await message.answer(
        f"✅ Объявление №{number} отправлено на модерацию",
        reply_markup=user_kb
    )

# ================= МОДЕРАЦИЯ =================
@dp.callback_query_handler(lambda c: c.data.startswith(("approve:", "reject:")))
async def moderation(call: types.CallbackQuery):
    action, post_id = call.data.split(":")
    admin = call.from_user.full_name

    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Нет прав", show_alert=True)
        return

    async with lock:
        pending = load_json(PENDING_FILE)
        post = pending.get(post_id)

        if not post or post["status"] != "pending":
            await call.answer("⚠️ Уже обработано")
            return

        post["status"] = "approved" if action == "approve" else "rejected"
        post["moderated_by"] = admin
        pending[post_id] = post
        save_json(PENDING_FILE, pending)

    number = post["number"]

    if post["status"] == "approved":
        if post["photos"]:
            media = [
                InputMediaPhoto(
                    media=pid,
                    caption=post["text"] if i == 0 else None
                )
                for i, pid in enumerate(post["photos"])
            ]
            await bot.send_media_group(CHANNEL_ID, media)
        else:
            await bot.send_message(CHANNEL_ID, post["text"])

        await bot.send_message(
            post["from_id"],
            f"✅ Объявление №{number} опубликовано\n👮 {admin}"
        )
        status = f"✅ Объявление №{number} одобрено\n👮 {admin}"
    else:
        await bot.send_message(
            post["from_id"],
            f"❌ Объявление №{number} отклонено\n👮 {admin}"
        )
        status = f"❌ Объявление №{number} отклонено\n👮 {admin}"

    for admin_id in ADMIN_IDS:
        try:
            await bot.edit_message_text(status, admin_id, call.message.message_id)
        except:
            pass

    await call.answer("Готово")

# ================= RUN =================
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
