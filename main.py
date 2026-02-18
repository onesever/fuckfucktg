import logging
import time
import sqlite3

from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher import FSMContext
from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto

# ================== НАСТРОЙКИ ==================
TOKEN = "8514017811:AAFKyBdlLjHTVlF1ql5Axe2WUZx2l9lgnFg"
CHANNEL_USERNAME = "@blackrussia_85"
CHANNEL_LINK = "https://t.me/blackrussia_85"
BOT_USERNAME = "blackrussia85_bot"

OWNER_ID = 724545647
MODERATORS_IDS = [
    5743211958,   # Bob1na
    6077303991,   # qwixx_am
    6621231808,  # MensClub4 реальный айди
    7244927531,   # creatorr13
    8390126598,   # wrezx
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
    username TEXT DEFAULT '',
    referrals INTEGER DEFAULT 0,
    last_post INTEGER DEFAULT 0
)
""")
conn.commit()

# ================== FSM ==================
class AdForm(StatesGroup):
    text = State()
    ask_photo = State()
    photos = State()
    confirm = State()

class BroadcastForm(StatesGroup):
    message = State()

# ================== STORAGE ==================
pending_ads = {}
processed_ads = {}
ad_counter = 0

# ================== КНОПКИ ==================
main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
main_kb.add("📢 Опубликовать объявление")
main_kb.add("📞 Связь с владельцем")
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

# ================== СТАРТ И ПОДПИСКА ==================
@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    args = message.get_args()
    referrer = int(args) if args.isdigit() else None

    cursor.execute("SELECT * FROM users WHERE user_id=?", (message.from_user.id,))
    user = cursor.fetchone()
    if not user:
        cursor.execute(
            "INSERT INTO users (user_id, referrer, username) VALUES (?, ?, ?)",
            (message.from_user.id, referrer, message.from_user.username)
        )
        conn.commit()
        if referrer and referrer != message.from_user.id:
            cursor.execute("UPDATE users SET referrals = referrals + 1 WHERE user_id=?", (referrer,))
            conn.commit()
    else:
        cursor.execute("UPDATE users SET username=? WHERE user_id=?", (message.from_user.username, message.from_user.id))
        conn.commit()

    if not await check_subscription(message.from_user.id):
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add("📢 Подписаться", "✅ Я подписался")
        await message.answer("❗ Для работы подпишитесь на канал", reply_markup=kb)
        return

    await message.answer("👋 Добро пожаловать!", reply_markup=main_kb)

@dp.message_handler(text="✅ Я подписался")
async def i_subscribed(message: types.Message):
    if await check_subscription(message.from_user.id):
        await message.answer("✅ Отлично! Теперь вы подписаны, пользуйтесь ботом:", reply_markup=main_kb)
    else:
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add("📢 Подписаться", "✅ Я подписался")
        await message.answer("❌ Вы ещё не подписаны на канал.", reply_markup=kb)

# ================== РЕФЕРАЛЫ ==================
@dp.message_handler(lambda message: message.text == "🎁 Рефералы")
async def referrals(message: types.Message):
    cursor.execute("SELECT * FROM users WHERE user_id=?", (message.from_user.id,))
    user = cursor.fetchone()
    if not user:
        cursor.execute("INSERT INTO users (user_id, username) VALUES (?, ?)", (message.from_user.id, message.from_user.username))
    else:
        cursor.execute("UPDATE users SET username=? WHERE user_id=?", (message.from_user.username, message.from_user.id))
    conn.commit()

    cursor.execute("SELECT referrals FROM users WHERE user_id=?", (message.from_user.id,))
    refs = cursor.fetchone()[0]

    level, cooldown = get_level(refs)

    cursor.execute("SELECT username, referrals FROM users ORDER BY referrals DESC LIMIT 5")
    top = cursor.fetchall()

    top_text = ""
    for i in range(5):
        if i < len(top):
            uname = top[i][0] if top[i][0] else "Неизвестно"
            top_text += f"{i+1}. @{uname} — {top[i][1]} людей\n"
        else:
            top_text += f"{i+1}.\n"

    rules = (
        "📌 Правила реферальной системы:\n"
        "— Новичок 👤: <30 приглашённых — КД 150 минут\n"
        "— Активный селлер 🔥: 30–99 приглашённых — КД 90 минут\n"
        "— Топ селлер 🏆: 100+ приглашённых — КД 30 минут\n"
        "Учитываются только реальные люди."
    )

    await message.answer(
        f"<b>🎁 Реферальная система</b>\n\n"
        f"Ваш уровень: {level}\n"
        f"Приглашено: {refs} людей\n"
        f"Ваш КД: {format_time(cooldown)}\n\n"
        f"Ваша ссылка:\nhttps://t.me/{BOT_USERNAME}?start={message.from_user.id}\n\n"
        f"<b>🏆 Топ 5</b>\n{top_text}\n\n"
        f"{rules}",
        reply_markup=main_kb
    )

# ================== ПОДАЧА ОБЪЯВЛЕНИЯ ==================
@dp.message_handler(text="📢 Опубликовать объявление")
async def start_ad(message: types.Message):
    cursor.execute("SELECT * FROM users WHERE user_id=?", (message.from_user.id,))
    user = cursor.fetchone()
    if not user:
        cursor.execute("INSERT INTO users (user_id, username) VALUES (?, ?)", (message.from_user.id, message.from_user.username))
        conn.commit()
    else:
        cursor.execute("UPDATE users SET username=? WHERE user_id=?", (message.from_user.username, message.from_user.id))
        conn.commit()

    if not await check_subscription(message.from_user.id):
        await message.answer("❗ Подпишитесь на канал.")
        return

    cursor.execute("SELECT referrals, last_post FROM users WHERE user_id=?", (message.from_user.id,))
    refs, last_post = cursor.fetchone()
    level, cooldown = get_level(refs)
    now = int(time.time())
    if now - last_post < cooldown:
        wait = cooldown - (now - last_post)
        await message.answer(f"⏳ Подождите {format_time(wait)}", reply_markup=main_kb)
        return

    await message.answer("✍️ Отправьте текст объявления.\n\n⚠️ Обязательно должен быть указан @username",
                         reply_markup=types.ReplyKeyboardRemove())
    await AdForm.text.set()

# ================== FSM ОБЪЯВЛЕНИЯ ==================
@dp.message_handler(state=AdForm.text, content_types=types.ContentTypes.TEXT)
async def get_text(message: types.Message, state: FSMContext):
    if "@" not in message.text:
        await message.answer("❗ В объявлении должен быть указан ваш @username")
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
    global ad_counter
    data = await state.get_data()
    user = call.from_user

    for ad in pending_ads.values():
        if ad["user"].id == user.id and ad["text"] == data["text"]:
            await call.answer("❌ Вы уже отправили такое объявление на модерацию.", show_alert=True)
            await state.finish()
            return

    ad_counter += 1
    ad_id = ad_counter
    cursor.execute("SELECT referrals FROM users WHERE user_id=?", (user.id,))
    refs = cursor.fetchone()[0]
    badge = "\n⭐ Топ селлер" if refs >= 100 else ""
    author = f"@{user.username}" if user.username else str(user.id)
    caption = f"🆕 Объявление №{ad_id}{badge}\nОт: {author}\n\n{data['text']}"

    pending_ads[ad_id] = {"user": user, "text": caption, "photos": data["photos"]}

    for mid in MODERATORS_IDS + [OWNER_ID]:
        try:
            if data["photos"]:
                media = [InputMediaPhoto(data["photos"][0], caption=caption)]
                for p in data["photos"][1:]:
                    media.append(InputMediaPhoto(p))
                await bot.send_media_group(mid, media)
                await bot.send_message(mid, "⬆️ Модерация", reply_markup=moderation_kb(ad_id))
            else:
                await bot.send_message(mid, caption, reply_markup=moderation_kb(ad_id))
        except:
            continue

    # В канал только текст без автора и номера
    if data["photos"]:
        media = [InputMediaPhoto(data["photos"][0], caption=data["text"])]
        for p in data["photos"][1:]:
            media.append(InputMediaPhoto(p))
        await bot.send_media_group(CHANNEL_USERNAME, media)
    else:
        await bot.send_message(CHANNEL_USERNAME, data["text"])

    cursor.execute("UPDATE users SET last_post=? WHERE user_id=?", (int(time.time()), user.id))
    conn.commit()
    await state.finish()
    await call.message.answer("✅ Отправлено на модерацию", reply_markup=main_kb)
    await call.answer()

# ================== МОДЕРАЦИЯ ==================
@dp.callback_query_handler(lambda c: c.data.startswith(("approve:", "reject:")))
async def moderate(call: types.CallbackQuery):
    if call.from_user.id not in MODERATORS_IDS and call.from_user.id != OWNER_ID:
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
    status = "ОДОБРЕНО" if action == "approve" else "ОТКЛОНЕНО"

    if action == "approve":
        if ad["photos"]:
            media = [InputMediaPhoto(ad["photos"][0], caption=ad["text"])]
            for p in ad["photos"][1:]:
                media.append(InputMediaPhoto(p))
            await bot.send_media_group(CHANNEL_USERNAME, media)
        else:
            await bot.send_message(CHANNEL_USERNAME, ad["text"])

    for mid in MODERATORS_IDS + [OWNER_ID]:
        try:
            await bot.send_message(mid, f"📌 Объявление №{ad_id} {status}\n👮 {call.from_user.full_name}")
        except:
            continue

    try:
        await bot.send_message(ad["user"].id, f"📌 Ваше объявление №{ad_id} {status}")
    except:
        pass

    await call.message.edit_reply_markup()
    await call.answer()

# ================== ДОПОЛНИТЕЛЬНЫЕ КНОПКИ ==================
@dp.message_handler(text="👮 Модераторы")
async def show_moderators(message: types.Message):
    admins = {
        "@onesever": "Владелец 👑",
        "@Bob1na": "Модератор",
        "@qwixx_am": "Модератор",
        "@MensClub4": "Модератор",
        "@creatorr13": "Модератор",
        "@wrezx": "Модератор"
    }
    text = "<b>Список модераторов и владельца:</b>\n\n"
    for uname, role in admins.items():
        text += f"👤 {uname} — {role}\n"
    await message.answer(text, reply_markup=main_kb)

@dp.message_handler(text="📞 Связь с владельцем")
async def contact_owner(message: types.Message):
    await message.answer(f"📬 Связь с владельцем:\n\n👑 Владелец: @onesever\nВы можете написать ему напрямую в Telegram.", reply_markup=main_kb)

# ================== BROADCAST ==================
@dp.message_handler(commands=["broadcast"])
async def start_broadcast(message: types.Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("❌ Только владелец может использовать эту команду.")
        return
    await message.answer("✉️ Отправьте текст рассылки для всех пользователей:")
    await BroadcastForm.message.set()

@dp.message_handler(state=BroadcastForm.message, content_types=types.ContentTypes.TEXT)
async def broadcast_send(message: types.Message, state: FSMContext):
    text_to_send = message.text
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    success = 0
    failed = 0
    for user in users:
        try:
            await bot.send_message(user[0], text_to_send)
            success += 1
        except:
            failed += 1
    await message.answer(f"📤 Рассылка завершена.\n✅ Успешно: {success}\n❌ Не доставлено: {failed}")
    await state.finish()

# ================== /USERS ==================
@dp.message_handler(commands=["users"])
async def count_users(message: types.Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("❌ Только владелец может использовать эту команду.")
        return
    cursor.execute("SELECT COUNT(*) FROM users")
    total = cursor.fetchone()[0]
    await message.answer(f"👥 Всего пользователей в боте: {total}")

# ================== RUN ==================
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
