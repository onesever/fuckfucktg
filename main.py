import logging
import json
import time
import asyncio
from collections import defaultdict

from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto
)

# ================= НАСТРОЙКИ =================
TOKEN = "8514017811:AAEK007dilGv0Etcvxp2HJhEMQ5npt22pps"

ADMIN_IDS = [724545647, 8390126598]
CHANNEL_ID = "@blackrussia_85"

SPAM_TIMEOUT = 600  # 10 минут

PENDING_FILE = "pending.json"
LAST_POST_FILE = "last_post.json"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

lock = asyncio.Lock()
albums = defaultdict(list)

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
user_kb.add("📢 Опубликовать объявление")
user_kb.add("📖 Помощь", "📞 Связь с админом")

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
        "📘 Пример:\n"
        "1️⃣ Куплю / Продам\n"
        "2️⃣ Цена\n"
        "3️⃣ Связь — @username"
    )

@dp.message_handler(lambda m: m.text == "📞 Связь с админом")
async def contact(message: types.Message):
    await message.answer("📬 Свяжитесь с администратором.")

@dp.message_handler(lambda m: m.text == "📢 Опубликовать объявление")
async def publish(message: types.Message):
    await message.answer("📝 Отправь текст или несколько фото с подписью.")

# ================= АЛЬБОМ =================
@dp.message_handler(content_types=types.ContentType.PHOTO)
async def handle_album(message: types.Message):
    if not message.media_group_id:
        await handle_single(message)
        return

    ok, wait = check_spam(message.from_user.id)
    if not ok:
        await message.answer(f"⏳ Подожди {wait // 60} мин.")
        return

    albums[message.media_group_id].append(message)
    await asyncio.sleep(1)

    album = albums.pop(message.media_group_id, [])
    if not album:
        return

    caption = album[0].caption or ""

    media = []
    for i, msg in enumerate(album):
        media.append(
            InputMediaPhoto(
                media=msg.photo[-1].file_id,
                caption=caption if i == 0 else None
            )
        )

    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("✅ Одобрить", callback_data="approve"),
        InlineKeyboardButton("❌ Отклонить", callback_data="reject")
    )

    for admin in ADMIN_IDS:
        sent = await bot.send_media_group(admin, media)
        await bot.send_message(admin, "🆕 Объявление", reply_markup=kb)

        pending = load_json(PENDING_FILE)
        pending[str(sent[0].message_id)] = {
            "type": "album",
            "media": [m.media for m in media],
            "caption": caption,
            "from_id": message.from_user.id,
            "status": "pending"
        }
        save_json(PENDING_FILE, pending)

    await message.answer("✅ Отправлено на модерацию")

# ================= ОДИНОЧНОЕ =================
async def handle_single(message: types.Message):
    ok, wait = check_spam(message.from_user.id)
    if not ok:
        await message.answer(f"⏳ Подожди {wait // 60} мин.")
        return

    payload = {
        "type": "text",
        "text": message.text,
        "from_id": message.from_user.id,
        "status": "pending"
    }

    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("✅ Одобрить", callback_data="approve"),
        InlineKeyboardButton("❌ Отклонить", callback_data="reject")
    )

    for admin in ADMIN_IDS:
        sent = await bot.send_message(admin, message.text, reply_markup=kb)
        pending = load_json(PENDING_FILE)
        pending[str(sent.message_id)] = payload
        save_json(PENDING_FILE, pending)

    await message.answer("✅ Отправлено на модерацию")

@dp.message_handler(content_types=types.ContentType.TEXT)
async def handle_text(message: types.Message):
    if message.text.startswith("📢") or message.text.startswith("📖") or message.text.startswith("📞"):
        return
    await handle_single(message)

# ================= МОДЕРАЦИЯ =================
@dp.callback_query_handler(lambda c: c.data in ["approve", "reject"])
async def moderation(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Нет прав", show_alert=True)
        return

    msg_id = str(call.message.message_id)
    admin_name = call.from_user.full_name

    async with lock:
        pending = load_json(PENDING_FILE)
        payload = pending.get(msg_id)

        if not payload or payload["status"] != "pending":
            await call.answer("Уже обработано")
            return

        payload["status"] = "approved" if call.data == "approve" else "rejected"
        payload["moderated_by"] = admin_name
        pending[msg_id] = payload
        save_json(PENDING_FILE, pending)

    if payload["status"] == "approved":
        if payload["type"] == "album":
            media = []
            for i, fid in enumerate(payload["media"]):
                media.append(
                    InputMediaPhoto(
                        media=fid,
                        caption=payload["caption"] if i == 0 else None
                    )
                )
            await bot.send_media_group(CHANNEL_ID, media)
        else:
            await bot.send_message(CHANNEL_ID, payload["text"])

        await bot.send_message(
            payload["from_id"],
            f"✅ Опубликовано\n👮 Администратор: {admin_name}"
        )
        status = f"✅ Одобрено\n👮 {admin_name}"
    else:
        await bot.send_message(
            payload["from_id"],
            f"❌ Отклонено\n👮 Администратор: {admin_name}"
        )
        status = f"❌ Отклонено\n👮 {admin_name}"

    for admin in ADMIN_IDS:
        try:
            await bot.edit_message_text(status, admin, call.message.message_id)
        except:
            pass

    await call.answer("Готово")

# ================= RUN =================
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)

