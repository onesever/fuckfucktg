import logging
import time
import asyncio
import sqlite3

from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardMarkup, InlineKeyboardMarkup,
    InlineKeyboardButton, InputMediaPhoto
)

# ================== НАСТРОЙКИ ==================

TOKEN = "8514017811:AAFKyBdlLjHTVlF1ql5Axe2WUZx2l9lgnFg"
CHANNEL_USERNAME = "@blackrussia_85"
CHANNEL_LINK = "https://t.me/blackrussia_85"
BOT_USERNAME = "blackrussia85_bot"

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

MAX_PHOTOS = 5

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN, parse_mode="HTML")
dp = Dispatcher(bot, storage=MemoryStorage())

# ================== DATABASE ==================

conn = sqlite3.connect("database.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    referrer INTEGER,
    referrals INTEGER DEFAULT 0,
    last_post INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS ads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    status TEXT DEFAULT 'pending'
)
""")

conn.commit()

# ================== FSM ==================

class AdForm(StatesGroup):
    text = State()
    ask_photo = State()
    photos = State()
    confirm = State()

# ================== ПАМЯТЬ ==================

pending_ads = {}
processed_ads = set()

# ================== КНОПКИ ==================

main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
main_kb.add("📢 Опубликовать объявление")
main_kb.add("📖 Помощь", "📞 Связь с владельцем")
main_kb.add("👮 Модераторы", "🎁 Рефералы")

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

# ================== УТИЛИТЫ ==================

def get_level(refs):
    if refs >= 100:
        return "🏆 Топ селлер", 30 * 60
    elif refs >= 30:
        return "🔥 Активный селлер", 90 * 60
    else:
        return "👤 Новичок", 150 * 60

def format_time(seconds):
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return f"{hours} ч {minutes} мин"

async def check_subscription(user_id):
    try:
        member = await bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ["member", "creator", "administrator"]
    except:
        return False

# ================== START ==================

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    args = message.get_args()
    referrer = int(args) if args.isdigit() else None

    cursor.execute("SELECT * FROM users WHERE user_id=?", (message.from_user.id,))
    user = cursor.fetchone()

    if not user:
        cursor.execute(
            "INSERT INTO users (user_id, referrer) VALUES (?, ?)",
            (message.from_user.id, referrer)
        )
        conn.commit()

        if referrer and referrer != message.from_user.id:
            cursor.execute(
                "UPDATE users SET referrals = referrals + 1 WHERE user_id=?",
                (referrer,)
            )
            conn.commit()

    if not await check_subscription(message.from_user.id):
        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton("📢 Подписаться", url=CHANNEL_LINK)
        )
        await message.answer("❗ Для работы подпишитесь на канал.", reply_markup=kb)
        return

    await message.answer("👋 Добро пожаловать!", reply_markup=main_kb)

# ================== ПОМОЩЬ ==================

@dp.message_handler(text="📖 Помощь")
async def help_msg(message: types.Message):
    await message.answer(
        "📌 <b>Как подать объявление</b>\n\n"
        "1️⃣ Опубликовать объявление\n"
        "2️⃣ Написать текст\n"
        "3️⃣ Добавить фото (по желанию)\n"
        "4️⃣ Подтвердить\n\n"
        "📌 Пример:\n"
        "Продам дом\nЦена: 17кк\nСвязь: @username\n\n"
        "⚠️ Обязательно указать @username",
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

# ================== РЕФЕРАЛЫ ==================

@dp.message_handler(text="🎁 Рефералы")
async def referrals(message: types.Message):
    cursor.execute("SELECT referrals FROM users WHERE user_id=?", (message.from_user.id,))
    row = cursor.fetchone()
    refs = row[0] if row else 0

    level, cooldown = get_level(refs)

    cursor.execute("SELECT user_id, referrals FROM users ORDER BY referrals DESC LIMIT 10")
    top = cursor.fetchall()

    top_text = ""
    for i, (uid, rcount) in enumerate(top, start=1):
        try:
            u = await bot.get_chat(uid)
            uname = f"@{u.username}" if u.username else u.full_name
        except:
            uname = str(uid)
        top_text += f"{i}. {uname} — {rcount} человек\n"

    await message.answer(
        f"<b>🎁 Реферальная система</b>\n\n"
        f"<b>Уровни:</b>\n"
        f"👤 Новичок — до 29 человек — КД 2ч 30м\n"
        f"🔥 Активный селлер — 30 человек — КД 1ч 30м\n"
        f"🏆 Топ селлер — 100 человек — КД 30м + ⭐ в посте\n\n"
        f"<b>Ваш уровень:</b> {level}\n"
        f"Приглашено: {refs} человек\n"
        f"Ваш КД: {format_time(cooldown)}\n\n"
        f"<b>Ваша ссылка:</b>\n"
        f"https://t.me/{BOT_USERNAME}?start={message.from_user.id}\n\n"
        f"<b>🏆 Топ 10:</b>\n{top_text}",
        reply_markup=main_kb
    )

# ================== ПОДАЧА ==================

@dp.message_handler(text="📢 Опубликовать объявление")
async def start_ad(message: types.Message):
    if not await check_subscription(message.from_user.id):
        await message.answer("❗ Подпишитесь на канал.")
        return

    cursor.execute("SELECT referrals, last_post FROM users WHERE user_id=?",
                   (message.from_user.id,))
    row = cursor.fetchone()
    if not row:
        return

    refs, last_post = row
    level, cooldown = get_level(refs)

    now = int(time.time())
    if now - last_post < cooldown:
        wait = cooldown - (now - last_post)
        await message.answer(f"⏳ Подождите {format_time(wait)}", reply_markup=main_kb)
        return

    await message.answer(
        "✍️ <b>Подача объявления</b>\n\n"
        "Отправьте текст объявления одним сообщением.\n\n"
        "📌 Пример:\n"
        "Продам дом\nЦена: 17кк\nСвязь: @username",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await AdForm.text.set()

@dp.message_handler(state=AdForm.text)
async def get_text(message: types.Message, state: FSMContext):
    if "@" not in message.text:
        await message.answer("❗ Укажите ваш @username в тексте.")
        return

    await state.update_data(text=message.text, photos=[])
    await message.answer("📸 Хотите добавить фото?", reply_markup=ask_photo_kb)
    await AdForm.ask_photo.set()

@dp.message_handler(state=AdForm.ask_photo, text="➡️ Без фото")
async def no_photo(message: types.Message, state: FSMContext):
    await show_preview(message, state)

@dp.message_handler(state=AdForm.ask_photo, text="➕ Добавить фото")
async def add_photo(message: types.Message):
    await message.answer("Отправьте до 5 фото и нажмите Готово", reply_markup=photo_done_kb)
    await AdForm.photos.set()

@dp.message_handler(state=AdForm.photos, content_types=types.ContentTypes.PHOTO)
async def get_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    if len(photos) < MAX_PHOTOS:
        photos.append(message.photo[-1].file_id)
        await state.update_data(photos=photos)

@dp.message_handler(state=AdForm.photos, text="✅ Готово")
async def photos_done(message: types.Message, state: FSMContext):
    await show_preview(message, state)

async def show_preview(message, state):
    data = await state.get_data()

    if data["photos"]:
        media = [InputMediaPhoto(data["photos"][0], caption=data["text"])]
        for p in data["photos"][1:]:
            media.append(InputMediaPhoto(p))
        await bot.send_media_group(message.chat.id, media)
    else:
        await message.answer(data["text"])

    await message.answer("Подтвердите:", reply_markup=confirm_kb)
    await AdForm.confirm.set()

# ================== ПОДТВЕРЖДЕНИЕ ==================

@dp.callback_query_handler(text="confirm", state=AdForm.confirm)
async def confirm(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user = call.from_user

    cursor.execute("INSERT INTO ads (user_id) VALUES (?)", (user.id,))
    conn.commit()
    ad_id = cursor.lastrowid

    user_tag = f"@{user.username}" if user.username else "без username"

    mod_caption = (
        f"🆕 <b>Объявление №{ad_id}</b>\n"
        f"👤 {user.full_name}\n"
        f"🔗 {user_tag}\n"
        f"🆔 {user.id}\n\n"
        f"{data['text']}"
    )

    channel_text = data["text"]

    pending_ads[ad_id] = {
        "user": user,
        "channel_text": channel_text,
        "mod_text": mod_caption,
        "photos": data["photos"]
    }

    for mid in MODERATORS:
        if data["photos"]:
            media = [InputMediaPhoto(data["photos"][0], caption=mod_caption)]
            for p in data["photos"][1:]:
                media.append(InputMediaPhoto(p))
            await bot.send_media_group(mid, media)
            await bot.send_message(mid, "⬆️ Модерация", reply_markup=moderation_kb(ad_id))
        else:
            await bot.send_message(mid, mod_caption, reply_markup=moderation_kb(ad_id))

    cursor.execute("UPDATE users SET last_post=? WHERE user_id=?",
                   (int(time.time()), user.id))
    conn.commit()

    await state.finish()
    await call.message.answer("✅ Отправлено на модерацию", reply_markup=main_kb)
    await call.answer()

@dp.callback_query_handler(text="cancel", state=AdForm.confirm)
async def cancel(call: types.CallbackQuery, state: FSMContext):
    await state.finish()
    await call.message.delete()
    await call.message.answer("❌ Отменено", reply_markup=main_kb)
    await call.answer()

# ================== МОДЕРАЦИЯ ==================

@dp.callback_query_handler(lambda c: c.data.startswith(("approve:", "reject:")))
async def moderate(call: types.CallbackQuery):
    if call.from_user.id not in MODERATORS:
        return

    action, ad_id = call.data.split(":")
    ad_id = int(ad_id)

    if ad_id in processed_ads:
        await call.answer("Уже обработано", show_alert=True)
        return

    cursor.execute("SELECT status FROM ads WHERE id=?", (ad_id,))
    row = cursor.fetchone()
    if not row or row[0] != "pending":
        await call.answer("Уже обработано", show_alert=True)
        return

    ad = pending_ads.get(ad_id)
    if not ad:
        return

    processed_ads.add(ad_id)

    if action == "approve":
        if ad["photos"]:
            media = [InputMediaPhoto(ad["photos"][0], caption=ad["channel_text"])]
            for p in ad["photos"][1:]:
                media.append(InputMediaPhoto(p))
            await bot.send_media_group(CHANNEL_USERNAME, media)
        else:
            await bot.send_message(CHANNEL_USERNAME, ad["channel_text"])
        status_text = "ОДОБРЕНО"
    else:
        status_text = "ОТКЛОНЕНО"

    cursor.execute("UPDATE ads SET status=? WHERE id=?", (status_text, ad_id))
    conn.commit()

    for mid in MODERATORS:
        await bot.send_message(
            mid,
            f"📌 Объявление №{ad_id} {status_text}\n"
            f"👮 {call.from_user.full_name}"
        )

    await call.message.edit_reply_markup()
    await call.answer("Готово")

# ================== СЕРВИС ==================

@dp.message_handler(commands=["users"])
async def users_cmd(message: types.Message):
    if message.from_user.id == OWNER_ID:
        cursor.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]
        await message.answer(f"👥 Пользователей: {count}")

@dp.message_handler(commands=["broadcast"])
async def broadcast(message: types.Message):
    if message.from_user.id != OWNER_ID:
        return

    text = message.get_args()
    if not text:
        await message.answer("❌ Напиши текст после команды")
        return

    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    sent = 0
    for user in users:
        try:
            await bot.send_message(user[0], text)
            sent += 1
            await asyncio.sleep(0.05)
        except:
            pass

    await message.answer(f"✅ Отправлено: {sent}")

# ================== RUN ==================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
