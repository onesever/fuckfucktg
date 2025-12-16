import asyncio
import json
import time
from collections import defaultdict

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InputMediaPhoto,
)

# ================= НАСТРОЙКИ =================
TOKEN = "8514017811:AAEK007dilGv0Etcvxp2HJhEMQ5npt22pps"  # <-- ВСТАВЬ НОВЫЙ ТОКЕН
ADMIN_IDS = [724545647, 8390126598]
CHANNEL_ID = "@blackrussia_85"

SPAM_TIMEOUT = 600  # 10 минут

PENDING_FILE = "pending.json"
LAST_POST_FILE = "last_post.json"

# ================= BOT =================
bot = Bot(token=TOKEN)
dp = Dispatcher()

LOCK = asyncio.Lock()
media_groups = defaultdict(list)

# ================= JSON =================
async def load_json(file):
    try:
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

async def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ================= КЛАВИАТУРА =================
user_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📢 Опубликовать объявление")],
        [KeyboardButton(text="📖 Помощь"), KeyboardButton(text="📞 Связь с админом")],
    ],
    resize_keyboard=True,
)

# ================= /start =================
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "👋 Привет!\n\n"
        "Отправь объявление (текст, фото или несколько фото).\n"
        "Администратор проверит его перед публикацией.",
        reply_markup=user_kb,
    )

# ================= КНОПКИ =================
@dp.message(F.text == "📖 Помощь")
async def help_msg(message: types.Message):
    await message.answer(
        "📘 *Пример объявления:*\n\n"
        "1️⃣ Куплю / Продам\n"
        "2️⃣ Цена\n"
        "3️⃣ Связь — @username",
        parse_mode="Markdown",
    )

@dp.message(F.text == "📞 Связь с админом")
async def contact(message: types.Message):
    await message.answer("📬 Напиши администратору в личные сообщения.")

@dp.message(F.text == "📢 Опубликовать объявление")
async def publish(message: types.Message):
    await message.answer("📝 Отправь текст, фото или альбом (несколько фото).")

# ================= АНТИСПАМ =================
async def check_spam(user_id: int):
    data = await load_json(LAST_POST_FILE)
    now = int(time.time())
    last = data.get(str(user_id), 0)

    if now - last < SPAM_TIMEOUT:
        wait = SPAM_TIMEOUT - (now - last)
        return False, wait

    data[str(user_id)] = now
    await save_json(LAST_POST_FILE, data)
    return True, 0

# ================= АЛЬБОМЫ (НЕСКОЛЬКО ФОТО) =================
@dp.message(F.media_group_id)
async def handle_album(message: types.Message):
    ok, wait = await check_spam(message.from_user.id)
    if not ok:
        await message.answer(f"⏳ Подожди {wait // 60} мин. перед новым объявлением.")
        return

    media_groups[message.media_group_id].append(message)
    await asyncio.sleep(1)

    album = media_groups.pop(message.media_group_id, [])
    if not album:
        return

    media = []
    caption = album[0].caption or ""

    for i, msg in enumerate(album):
        media.append(
            InputMediaPhoto(
                media=msg.photo[-1].file_id,
                caption=caption if i == 0 else None,
            )
        )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Одобрить", callback_data="approve"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data="reject"),
            ]
        ]
    )

    for admin in ADMIN_IDS:
        sent = await bot.send_media_group(admin, media)
        await bot.send_message(admin, "🆕 Альбом на модерацию", reply_markup=kb)

        pending = await load_json(PENDING_FILE)
        pending[str(sent[0].message_id)] = {
            "type": "album",
            "media": [m.media for m in media],
            "from_id": message.from_user.id,
        }
        await save_json(PENDING_FILE, pending)

    await message.answer("✅ Альбом отправлен на модерацию!")

# ================= ОДИНОЧНЫЕ СООБЩЕНИЯ =================
@dp.message(F.chat.type == "private")
async def handle_message(message: types.Message):
    if message.text in ["📢 Опубликовать объявление", "📖 Помощь", "📞 Связь с админом"]:
        return

    ok, wait = await check_spam(message.from_user.id)
    if not ok:
        await message.answer(f"⏳ Подожди {wait // 60} мин. перед новым объявлением.")
        return

    payload = {
        "from_id": message.from_user.id,
        "type": None,
        "file_id": None,
        "text": None,
    }

    if message.photo:
        payload["type"] = "photo"
        payload["file_id"] = message.photo[-1].file_id
    elif message.text:
        payload["type"] = "text"
        payload["text"] = message.text
    else:
        await message.answer("❌ Тип сообщения не поддерживается.")
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Одобрить", callback_data="approve"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data="reject"),
            ]
        ]
    )

    for admin in ADMIN_IDS:
        if payload["type"] == "photo":
            sent = await bot.send_photo(admin, payload["file_id"], reply_markup=kb)
        else:
            sent = await bot.send_message(admin, payload["text"], reply_markup=kb)

        pending = await load_json(PENDING_FILE)
        pending[str(sent.message_id)] = payload
        await save_json(PENDING_FILE, pending)

    await message.answer("✅ Объявление отправлено на модерацию!")

# ================= МОДЕРАЦИЯ =================
@dp.callback_query(F.data.in_(["approve", "reject"]))
async def moderation(query: types.CallbackQuery):
    if query.from_user.id not in ADMIN_IDS:
        await query.answer("❌ Нет прав", show_alert=True)
        return

    pending = await load_json(PENDING_FILE)
    payload = pending.pop(str(query.message.message_id), None)
    await save_json(PENDING_FILE, pending)

    if not payload:
        await query.answer("⚠️ Уже обработано")
        return

    if query.data == "approve":
        if payload["type"] == "photo":
            await bot.send_photo(CHANNEL_ID, payload["file_id"])
        elif payload["type"] == "text":
            await bot.send_message(CHANNEL_ID, payload["text"])
        elif payload["type"] == "album":
            media = [InputMediaPhoto(media=m) for m in payload["media"]]
            await bot.send_media_group(CHANNEL_ID, media)

        await bot.send_message(payload["from_id"], "✅ Ваше объявление опубликовано!")
        await query.answer("✅ Опубликовано")
    else:
        await bot.send_message(payload["from_id"], "❌ Ваше объявление отклонено.")
        await query.answer("❌ Отклонено")

    await bot.edit_message_reply_markup(
        query.message.chat.id,
        query.message.message_id,
        reply_markup=None,
    )

# ================= ЗАПУСК =================
async def main():
    print("🤖 Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
