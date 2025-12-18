import logging
import time
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup

# ================== НАСТРОЙКИ ==================

TOKEN = "8514017811:AAEgZ5V_8mX4vzw2FGhI-En-rzgZN5O5LiQ"
CHANNEL_ID = "@blackrussia_85"

OWNER_USERNAME = "@onesever"

MODERATORS = [
    724545647,     # владелец
    8390126598,
    7946280692,
    7244927531,
]

ANTISPAM_SECONDS = 2 * 60 * 60  # 2 часа

# ================== INIT ==================

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

# ================== ХРАНИЛИЩА ==================

users = set()
last_post_time = {}
pending_ads = {}
processed_ads = {}
ad_counter = 0

# ================== КЛАВИАТУРЫ ==================

main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
main_kb.add("📢 Опубликовать объявление")
main_kb.add("📖 Помощь", "📞 Связь с владельцем")
main_kb.add("👮 Модераторы")

confirm_kb = InlineKeyboardMarkup()
confirm_kb.add(
    InlineKeyboardButton("✅ Одобрить", callback_data="approve"),
    InlineKeyboardButton("❌ Отклонить", callback_data="reject")
)

def format_time(sec):
    h = sec // 3600
    m = (sec % 3600) // 60
    return f"{h} ч {m} мин" if h > 0 else f"{m} мин"

# ================== START ==================

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    users.add(message.from_user.id)
    await message.answer(
        "👋 Добро пожаловать!\n\n"
        "Здесь можно подать объявление для публикации.",
        reply_markup=main_kb
    )

# ================== ИНФО ==================

@dp.message_handler(text="📖 Помощь")
async def help_msg(message: types.Message):
    await message.answer(
        "📌 <b>Как подать объявление</b>\n\n"
        "1️⃣ Нажмите «Опубликовать объявление»\n"
        "2️⃣ Отправьте текст\n"
        "3️⃣ Дождитесь модерации\n\n"
        "⏳ 1 объявление раз в 2 часа"
    )

@dp.message_handler(text="📞 Связь с владельцем")
async def owner(message: types.Message):
    await message.answer(f"👑 Владелец: {OWNER_USERNAME}")

@dp.message_handler(text="👮 Модераторы")
async def mods(message: types.Message):
    await message.answer(
        "👮 <b>Модераторы</b>\n\n"
        "👑 Владелец:\n@onesever\n\n"
        "🛡 Модераторы:\n"
        "@creatorr13\n"
        "@krasnov_hub\n"
        "@wrezx"
    )

# ================== ПОДАЧА ОБЪЯВЛЕНИЯ ==================

@dp.message_handler(text="📢 Опубликовать объявление")
async def publish(message: types.Message):
    users.add(message.from_user.id)

    now = time.time()
    uid = message.from_user.id

    if uid in last_post_time:
        diff = int(now - last_post_time[uid])
        if diff < ANTISPAM_SECONDS:
            await message.answer(
                f"⏳ Повторная подача через {format_time(ANTISPAM_SECONDS - diff)}"
            )
            return

    await message.answer(
        "✍️ Отправьте текст объявления\n\n"
        "Пример:\n"
        "1) Продам: Дом\n"
        "2) Цена: 11.000.000\n"
        "3) Связь: @username",
        reply_markup=types.ReplyKeyboardRemove()
    )

# ================== ПОЛУЧЕНИЕ ТЕКСТА ==================

@dp.message_handler(content_types=types.ContentTypes.TEXT)
async def get_ad(message: types.Message):
    users.add(message.from_user.id)

    if message.text.startswith("/"):
        return

    global ad_counter
    ad_counter += 1
    ad_id = ad_counter

    pending_ads[ad_id] = {
        "text": message.text,
        "user_id": message.from_user.id,
        "username": message.from_user.username
    }

    text = (
        f"🆕 <b>Объявление №{ad_id}</b>\n"
        f"👤 @{message.from_user.username} | ID {message.from_user.id}\n\n"
        f"{message.text}"
    )

    for mid in MODERATORS:
        await bot.send_message(mid, text, reply_markup=confirm_kb)

    last_post_time[message.from_user.id] = time.time()

    await message.answer("✅ Объявление отправлено на модерацию", reply_markup=main_kb)

# ================== МОДЕРАЦИЯ ==================

@dp.callback_query_handler(lambda c: c.data in ["approve", "reject"])
async def moderate(call: types.CallbackQuery):
    if call.from_user.id not in MODERATORS:
        return

    ad_id = list(pending_ads.keys())[-1]

    if ad_id in processed_ads:
        await call.answer("⚠️ Уже обработано", show_alert=True)
        return

    ad = pending_ads[ad_id]
    processed_ads[ad_id] = call.from_user.full_name

    if call.data == "approve":
        await bot.send_message(CHANNEL_ID, ad["text"])
        await bot.send_message(ad["user_id"], f"✅ Объявление №{ad_id} опубликовано")
        status = "ОДОБРЕНО"
    else:
        await bot.send_message(ad["user_id"], f"❌ Объявление №{ad_id} отклонено")
        status = "ОТКЛОНЕНО"

    for mid in MODERATORS:
        await bot.send_message(
            mid,
            f"📌 Объявление №{ad_id} {status}\n"
            f"👮 {call.from_user.full_name}"
        )

    await call.message.edit_reply_markup()
    await call.answer("Готово")

# ================== USERS / BROADCAST ==================

@dp.message_handler(commands=["users"])
async def users_cmd(message: types.Message):
    if message.from_user.id not in MODERATORS:
        return
    await message.answer(f"👥 Пользователей в боте: <b>{len(users)}</b>")

@dp.message_handler(commands=["broadcast"])
async def broadcast(message: types.Message):
    if message.from_user.id not in MODERATORS:
        return

    text = message.get_args()
    if not text:
        await message.answer("❗ /broadcast текст")
        return

    ok = bad = 0
    for uid in users:
        try:
            await bot.send_message(uid, text)
            ok += 1
        except:
            bad += 1

    await message.answer(f"📣 Рассылка завершена\n✅ {ok}\n❌ {bad}")

# ================== RUN ==================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
