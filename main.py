import logging
import json
import time
import asyncio
from collections import defaultdict

from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto
)

# ================= НАСТРОЙКИ =================
TOKEN = "ТУТ_ТВОЙ_ТОКЕН"

ADMIN_IDS = [724545647, 8390126598]
CHANNEL_ID = "@blackrussia_85"

CONTACT_ADMIN = "@onesever"

SPAM_TIMEOUT = 600  # 10 минут

PENDING_FILE = "pending.json"
LAST_POST_FILE = "last_post.json"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

albums = defaultdict(list)
lock = asyncio.Lock()

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

# ================= КЛАВИАТУРА =================
user_kb = ReplyKeyboardMarkup(resize_keyboard=True)
user_kb.add(KeyboardButton("📢 Опубликовать объявление"))
user_kb.add(KeyboardButton("📖 Помощь"), KeyboardButton("📞 Связь с админом"))

# ================= АНТИСПАМ =================
def check_spam(user_id):
    data = load_json(LAST_POST_FILE)
    now = int(time.time())
    last = data.get(str(user_id), 0)

    if now - last < SPAM_TIMEOUT:
        return False, SPAM_TIMEOUT - (now - last)

    data[str(user_id)] = now
    save_json(LAST_POST_FILE, data)
    return True, 0

# ================= START =================
@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer(
        "👋 Привет!\n\n"
        "Отправь объявление (текст или несколько фото с текстом).\n"
        "Администратор проверит его перед публикацией.",
        reply_markup=user_kb
    )

# ================= КНОПКИ =================
@dp.message_handler(lambda m: m.text == "📖 Помощь")
async def help_msg(message: types.Message):
    await message.answer(
        "📘 Пример объявления:\n\n"
        "1️⃣ Куплю / Продам\n"
        "2️⃣ Цена\n"
        "3️⃣ Связь — @username"
    )

@dp.message_handler(lambda m: m.text == "📞 Связь с админом")
async def contact_admin(message: types.Message):
    await message.answer(
        f"📞 Связь с администратором:\n👉 {CONTACT_ADMIN}"
    )

@dp.message_handler(lambda m: m.text == "📢 Опубликовать объявление")
async def publish_info(message: types.Message):
    await message.answer(
        "📝 Отправь текст или несколько фото с подписью."
    )

# ================= АЛЬБОМ =================
@dp.message_handler(content_types=types.ContentType.PHOTO)
async def handle_album(message: types.Message):
    if not message.media_group_id:
        await handle_text(message)
        return

    albums[message.media_group_id].append(message)
    await asyncio.sleep(1)

    album = albums.pop(message.media_group_id, [])
    if not album:
        return

    ok, wait = check_spam(message.from_user.id)
    if not ok:
        await message.answer(f"⏳ Подожди {wait // 60} мин.")
        return

    caption = album[0].caption or ""
    post_id = str(int(time.time() * 1000))

    media = [
        InputMediaPhoto(
            media=msg.photo[-1].file_id,
            caption=caption if i == 0 else None
        )
        for i, msg in enumerate(album)
    ]

    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("✅ Одобрить", callback_data=f"approve:{post_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject:{post_id}")
    )

    pending = load_json(PENDING_FILE)
    pending[post_id] = {
        "type": "album",
        "media": [m.media for m in media],
        "caption": caption,
        "from_id": message.from_user.id,
        "status": "pending"
    }
    save_json(PENDING_FILE, pending)

    for admin in ADMIN_IDS:
        await bot.send_media_group(admin, media)
        await bot.send_message(admin, "🆕 Объявление", reply_markup=kb)

    await message.answer("✅ Объявление отправлено на модерацию!")

# ================= ТЕКСТ =================
@dp.message_handler(content_types=types.ContentType.TEXT)
async def handle_text(message: types.Message):
    if message.text.startswith("📢") or message.text.startswith("📖") or message.text.startswith("📞"):
        return

    ok, wait = check_spam(message.from_user.id)
    if not ok:
        await message.answer(f"⏳ Подожди {wait // 60} мин.")
        return

    post_id = str(int(time.time() * 1000))

    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("✅ Одобрить", callback_data=f"approve:{post_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject:{post_id}")
    )

    pending = load_json(PENDING_FILE)
    pending[post_id] = {
        "type": "text",
        "text": message.text,
        "from_id": message.from_user.id,
        "status": "pending"
    }
    save_json(PENDING_FILE, pending)

    for admin in ADMIN_IDS:
        await bot.send_message(admin, message.text, reply_markup=kb)

    await message.answer("✅ Объявление отправлено на модерацию!")

# ================= МОДЕРАЦИЯ =================
@dp.callback_query_handler(lambda c: c.data.startswith(("approve:", "reject:")))
async def moderation(call: types.CallbackQuery):
    action, post_id = call.data.split(":")
    admin_name = call.from_user.full_name

    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Нет прав", show_alert=True)
        return

    async with lock:
        pending = load_json(PENDING_FILE)
        payload = pending.get(post_id)

        if not payload or payload["status"] != "pending":
            await call.answer("⚠️ Уже обработано")
            return

        payload["status"] = "approved" if action == "approve" else "rejected"
        payload["moderated_by"] = admin_name
        pending[post_id] = payload
        save_json(PENDING_FILE, pending)

    if payload["status"] == "approved":
        if payload["type"] == "album":
            media = [
                InputMediaPhoto(
                    media=fid,
                    caption=payload["caption"] if i == 0 else None
                )
                for i, fid in enumerate(payload["media"])
            ]
            await bot.send_media_group(CHANNEL_ID, media)
        else:
            await bot.send_message(CHANNEL_ID, payload["text"])

        await bot.send_message(
            payload["from_id"],
            f"✅ Ваше объявление опубликовано\n👮 Администратор: {admin_name}"
        )

        status_text = f"✅ Одобрено\n👮 {admin_name}"
    else:
        await bot.send_message(
            payload["from_id"],
            f"❌ Ваше объявление отклонено\n👮 Администратор: {admin_name}"
        )
        status_text = f"❌ Отклонено\n👮 {admin_name}"

    for admin in ADMIN_IDS:
        try:
            await bot.edit_message_text(status_text, admin, call.message.message_id)
        except:
            pass

    await call.answer("Готово")

# ================= RUN =================
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)


