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

# ================= НАСТРОЙКИ =================

TOKEN = "8514017811:AAFKyBdlLjHTVlF1ql5Axe2WUZx2l9lgnFg"
CHANNEL_USERNAME = "@blackrussia_85"
CHANNEL_LINK = "https://t.me/blackrussia_85"
BOT_USERNAME = "blackrussia85_bot"

OWNER_ID = 724545647

MODERATORS = [
    724545647,
    7244927531,
    8390126598,
    6077303991,
    5743211958,
    6621231808,
]

MAX_PHOTOS = 5

# Уровни (в секундах)
COOLDOWN_NEWBIE = 2 * 60 * 60 + 30 * 60      # 2ч 30м
COOLDOWN_ACTIVE = 1 * 60 * 60 + 30 * 60     # 1ч 30м
COOLDOWN_TOP = 30 * 60                      # 30м

# ================= INIT =================

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN, parse_mode="HTML")
dp = Dispatcher(bot, storage=MemoryStorage())

# ================= DATABASE =================

conn = sqlite3.connect("database.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    referrals INTEGER DEFAULT 0,
    invited_by INTEGER,
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

# ================= FSM =================

class AdForm(StatesGroup):
    text = State()
    ask_photo = State()
    photos = State()
    confirm = State()

# ================= STORAGE =================

pending_ads = {}
processed_ads = set()

# ================= КЛАВИАТУРЫ =================

main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
main_kb.add("📢 Опубликовать объявление")
main_kb.add("🎁 Рефералы")
main_kb.add("📖 Помощь", "📞 Связь с владельцем")
main_kb.add("👮 Модераторы")

subscribe_kb = InlineKeyboardMarkup().add(
    InlineKeyboardButton("📢 Подписаться", url=CHANNEL_LINK)
).add(
    InlineKeyboardButton("✅ Я подписался", callback_data="check_sub")
)

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

def subscribe_post_kb():
    return InlineKeyboardMarkup().add(
        InlineKeyboardButton(
            "📢 Подписаться на Б/У рынок IZHEVSK",
            url=CHANNEL_LINK
        )
    )

# ================= УТИЛИТЫ =================

def format_time(sec):
    h = sec // 3600
    m = (sec % 3600) // 60
    return f"{h}ч {m}м" if h else f"{m}м"

def get_level(refs):
    if refs >= 100:
        return "🏆 <b>ТОП СЕЛЛЕР</b>", COOLDOWN_TOP
    elif refs >= 30:
        return "🔥 <b>АКТИВНЫЙ СЕЛЛЕР</b>", COOLDOWN_ACTIVE
    else:
        return None, COOLDOWN_NEWBIE

async def check_subscription(user_id):
    try:
        member = await bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

# ================= START =================

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    args = message.get_args()
    user_id = message.from_user.id

    cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    user = cursor.fetchone()

    if not user:
        invited_by = None
        if args.isdigit():
            inviter = int(args)
            if inviter != user_id:
                invited_by = inviter

        cursor.execute(
            "INSERT INTO users (user_id, invited_by) VALUES (?, ?)",
            (user_id, invited_by)
        )
        conn.commit()

    if not await check_subscription(user_id):
        await message.answer(
            "❌ Для использования бота подпишитесь на канал:",
            reply_markup=subscribe_kb
        )
        return

    await message.answer("Добро пожаловать!", reply_markup=main_kb)

@dp.callback_query_handler(lambda c: c.data == "check_sub")
async def check_sub(call: types.CallbackQuery):
    user_id = call.from_user.id

    if not await check_subscription(user_id):
        await call.answer("Вы ещё не подписаны.", show_alert=True)
        return

    cursor.execute("SELECT invited_by FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()

    if row and row[0]:
        inviter = row[0]
        cursor.execute(
            "UPDATE users SET referrals = referrals + 1 WHERE user_id=?",
            (inviter,)
        )
        cursor.execute(
            "UPDATE users SET invited_by=NULL WHERE user_id=?",
            (user_id,)
        )
        conn.commit()

    await call.message.delete()
    await call.message.answer("✅ Подписка подтверждена!", reply_markup=main_kb)
    # ================= ИНФО =================

@dp.message_handler(lambda m: m.text == "📖 Помощь")
async def help_msg(message: types.Message):
    await message.answer(
        "📌 <b>Как подать объявление</b>\n\n"
        "1️⃣ Нажмите «Опубликовать объявление»\n"
        "2️⃣ Отправьте текст\n"
        "3️⃣ Добавьте фото (по желанию)\n"
        "4️⃣ Подтвердите\n\n"
        "⚠️ В объявлении ОБЯЗАТЕЛЬНО должен быть указан ваш @username\n"
        "⏳ КД зависит от вашего уровня",
        reply_markup=main_kb
    )

@dp.message_handler(lambda m: m.text == "📞 Связь с владельцем")
async def owner_contact(message: types.Message):
    await message.answer("👑 Владелец: @onesever", reply_markup=main_kb)

@dp.message_handler(lambda m: m.text == "👮 Модераторы")
async def moderators_list(message: types.Message):
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

# ================= ПОДАЧА =================

@dp.message_handler(lambda m: m.text == "📢 Опубликовать объявление")
async def create_ad(message: types.Message):
    user_id = message.from_user.id

    if not await check_subscription(user_id):
        await message.answer("❌ Нужно быть подписанным на канал.")
        return

    cursor.execute("SELECT referrals, last_post FROM users WHERE user_id=?", (user_id,))
    refs, last_post = cursor.fetchone()

    level_tag, cooldown = get_level(refs)

    now = int(time.time())
    if now - last_post < cooldown:
        left = cooldown - (now - last_post)
        await message.answer(f"⏳ Подождите {format_time(left)}")
        return

    await message.answer(
        "✍️ <b>Введите текст объявления</b>\n\n"
        "📌 Пример:\n"
        "Продам дом в Бусаево\n"
        "Цена: 17кк\n"
        "Связь: @username\n\n"
        "⚠️ Username обязателен!",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await AdForm.text.set()

@dp.message_handler(state=AdForm.text)
async def ad_text(message: types.Message, state: FSMContext):
    if not message.from_user.username:
        await message.answer("❌ У вас нет username в Telegram.")
        return

    if f"@{message.from_user.username}" not in message.text:
        await message.answer("❌ В тексте должен быть указан именно ВАШ @username.")
        return

    await state.update_data(text=message.text, photos=[])
    await message.answer("Добавить фото?", reply_markup=ask_photo_kb)
    await AdForm.ask_photo.set()

@dp.message_handler(lambda m: m.text == "➕ Добавить фото", state=AdForm.ask_photo)
async def add_photo(message: types.Message):
    await message.answer("📸 Отправьте до 5 фото. Затем нажмите «Готово».", reply_markup=photo_done_kb)
    await AdForm.photos.set()

@dp.message_handler(lambda m: m.text == "➡️ Без фото", state=AdForm.ask_photo)
async def no_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await message.answer(
        f"🔍 <b>Предпросмотр</b>\n\n{data['text']}",
        reply_markup=confirm_kb
    )
    await AdForm.confirm.set()

@dp.message_handler(content_types=["photo"], state=AdForm.photos)
async def handle_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])

    if len(photos) >= MAX_PHOTOS:
        await message.answer("❌ Максимум 5 фото.")
        return

    photos.append(message.photo[-1].file_id)
    await state.update_data(photos=photos)
    await message.answer(f"Фото добавлено ({len(photos)}/{MAX_PHOTOS})")

@dp.message_handler(lambda m: m.text == "✅ Готово", state=AdForm.photos)
async def photos_done(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await message.answer(
        f"🔍 <b>Предпросмотр</b>\n\n{data['text']}",
        reply_markup=confirm_kb
    )
    await AdForm.confirm.set()

@dp.callback_query_handler(lambda c: c.data == "cancel", state=AdForm.confirm)
async def cancel_ad(call: types.CallbackQuery, state: FSMContext):
    await state.finish()
    await call.message.edit_text("❌ Подача отменена.")
    await call.message.answer("Главное меню:", reply_markup=main_kb)

@dp.callback_query_handler(lambda c: c.data == "confirm", state=AdForm.confirm)
async def confirm_ad(call: types.CallbackQuery, state: FSMContext):
    user = call.from_user
    data = await state.get_data()

    cursor.execute("INSERT INTO ads (user_id) VALUES (?)", (user.id,))
    ad_id = cursor.lastrowid
    conn.commit()

    pending_ads[ad_id] = data
    await state.finish()

    mod_text = (
        f"📢 <b>Новое объявление №{ad_id}</b>\n\n"
        f"👤 @{user.username}\n"
        f"🆔 ID: {user.id}\n\n"
        f"{data['text']}"
    )

    for mod in MODERATORS:
        try:
            await bot.send_message(mod, mod_text, reply_markup=moderation_kb(ad_id))
        except:
            pass

    await call.message.edit_text("✅ Отправлено на модерацию.")
    await call.message.answer("Главное меню:", reply_markup=main_kb)

# ================= МОДЕРАЦИЯ =================

@dp.callback_query_handler(lambda c: c.data.startswith("approve:"))
async def approve(call: types.CallbackQuery):
    ad_id = int(call.data.split(":")[1])

    if ad_id in processed_ads:
        await call.answer("Уже обработано.", show_alert=True)
        return

    processed_ads.add(ad_id)

    cursor.execute("SELECT user_id FROM ads WHERE id=?", (ad_id,))
    row = cursor.fetchone()
    if not row:
        return

    user_id = row[0]
    data = pending_ads.get(ad_id)
    if not data:
        return

    cursor.execute("SELECT referrals FROM users WHERE user_id=?", (user_id,))
    refs = cursor.fetchone()[0]
    tag, _ = get_level(refs)

    final_text = data["text"]
    if tag:
        final_text = f"{tag}\n\n{final_text}"

    if data["photos"]:
        media = [InputMediaPhoto(data["photos"][0], caption=final_text)]
        for p in data["photos"][1:]:
            media.append(InputMediaPhoto(p))
        await bot.send_media_group(CHANNEL_USERNAME, media)
        await bot.send_message(CHANNEL_USERNAME, "⬆️", reply_markup=subscribe_post_kb())
    else:
        await bot.send_message(
            CHANNEL_USERNAME,
            final_text,
            reply_markup=subscribe_post_kb()
        )

    cursor.execute("UPDATE ads SET status='approved' WHERE id=?", (ad_id,))
    cursor.execute("UPDATE users SET last_post=? WHERE user_id=?", (int(time.time()), user_id))
    conn.commit()

    await bot.send_message(user_id, f"✅ Ваше объявление №{ad_id} одобрено.")

    for mod in MODERATORS:
        try:
            await bot.send_message(
                mod,
                f"📌 Объявление №{ad_id} ОДОБРЕНО\n"
                f"👮 Модератор: @{call.from_user.username}"
            )
        except:
            pass

    await call.message.edit_reply_markup()

@dp.callback_query_handler(lambda c: c.data.startswith("reject:"))
async def reject(call: types.CallbackQuery):
    ad_id = int(call.data.split(":")[1])

    if ad_id in processed_ads:
        await call.answer("Уже обработано.", show_alert=True)
        return

    processed_ads.add(ad_id)

    cursor.execute("SELECT user_id FROM ads WHERE id=?", (ad_id,))
    user_id = cursor.fetchone()[0]

    cursor.execute("UPDATE ads SET status='rejected' WHERE id=?", (ad_id,))
    conn.commit()

    await bot.send_message(user_id, f"❌ Ваше объявление №{ad_id} отклонено.")

    for mod in MODERATORS:
        try:
            await bot.send_message(
                mod,
                f"📌 Объявление №{ad_id} ОТКЛОНЕНО\n"
                f"👮 Модератор: @{call.from_user.username}"
            )
        except:
            pass

    await call.message.edit_reply_markup()

# ================= РЕФЕРАЛЫ =================

@dp.message_handler(lambda m: m.text == "🎁 Рефералы")
async def referrals(message: types.Message):
    user_id = message.from_user.id

    cursor.execute("SELECT referrals FROM users WHERE user_id=?", (user_id,))
    refs = cursor.fetchone()[0]

    text = (
        f"👥 Вы пригласили: {refs} человек\n\n"
        f"🔗 Ваша ссылка:\n"
        f"https://t.me/{BOT_USERNAME}?start={user_id}\n\n"
        "🏅 Уровни:\n"
        "👤 Новичок — КД 2ч 30м\n"
        "🔥 Активный селлер (30 человек) — КД 1ч 30м\n"
        "🏆 Топ селлер (100 человек) — КД 30м\n"
        "⭐ Отметка в посте только у ТОП СЕЛЛЕРА\n\n"
    )

    cursor.execute("SELECT user_id, referrals FROM users ORDER BY referrals DESC LIMIT 10")
    top = cursor.fetchall()

    text += "🏆 Топ 10:\n"
    for i, (uid, r) in enumerate(top, 1):
        try:
            user = await bot.get_chat(uid)
            name = f"@{user.username}" if user.username else "Без username"
        except:
            name = "Неизвестно"
        text += f"{i}. {name} — {r}\n"

    await message.answer(text)

# ================= АДМИН =================

@dp.message_handler(commands=["users"])
async def users_count(message: types.Message):
    if message.from_user.id != OWNER_ID:
        return
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    await message.answer(f"👥 Пользователей: {count}")

@dp.message_handler(commands=["broadcast"])
async def broadcast(message: types.Message):
    if message.from_user.id != OWNER_ID:
        return

    text = message.get_args()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    for (uid,) in users:
        try:
            await bot.send_message(uid, text)
        except:
            pass

    await message.answer("✅ Рассылка завершена.")

# ================= ЗАПУСК =================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
