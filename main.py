import asyncio
import json
import time
from aiogram import Bot, Dispatcher, types
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.utils import executor

TOKEN = "8514017811:AAFCXcQHVjZsY_cwrKo-qi9NkvasDtBdfbo"
CHANNEL_ID = "@blackrussia_85"

# Владелец + модераторы (ID)
ADMIN_IDS = [
    724545647,
    8390126598,
    7946280692,
    7244927531
]

DATA_FILE = "data.json"

# ----------------- ХРАНИЛИЩЕ -----------------

def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {
            "posts": {},
            "counter": 0,
            "last_post_time": {},
            "users": []
        }

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ----------------- БОТ -----------------

bot = Bot(TOKEN)
dp = Dispatcher(bot)

# ----------------- КЛАВИАТУРЫ -----------------

user_kb = ReplyKeyboardMarkup(resize_keyboard=True)
user_kb.add("📢 Опубликовать объявление")
user_kb.add("📘 Помощь", "📞 Связь с владельцем")
user_kb.add("👥 Модераторы")

def moderation_kb(post_id):
    return InlineKeyboardMarkup().add(
        InlineKeyboardButton("✅ Одобрить", callback_data=f"approve:{post_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject:{post_id}")
    )

def confirm_kb():
    return InlineKeyboardMarkup().add(
        InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_post"),
        InlineKeyboardButton("❌ Отменить", callback_data="cancel_post")
    )

# ----------------- /start -----------------

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    data = load_data()
    uid = str(message.from_user.id)
    if uid not in data["users"]:
        data["users"].append(uid)
        save_data(data)

    await message.answer(
        "👋 Добро пожаловать!\n\n"
        "Здесь вы можете подать объявление для публикации.\n"
        "Все объявления проходят модерацию.",
        reply_markup=user_kb
    )

# ----------------- КНОПКИ -----------------

@dp.message_handler(text="📘 Помощь")
async def help_msg(message: types.Message):
    await message.answer(
        "📌 *Инструкция по подаче объявления*\n\n"
        "1️⃣ Сначала отправляете ТЕКСТ\n"
        "2️⃣ Потом добавляете ФОТО (по желанию)\n"
        "3️⃣ Проверяете предпросмотр\n"
        "4️⃣ Подтверждаете\n\n"
        "⏳ Антиспам: 1 объявление раз в 2 часа",
        parse_mode="Markdown"
    )

@dp.message_handler(text="📞 Связь с владельцем")
async def owner_contact(message: types.Message):
    await message.answer("👑 Владелец: @onesever")

@dp.message_handler(text="👥 Модераторы")
async def moderators(message: types.Message):
    await message.answer(
        "👥 *Модераторы проекта:*\n\n"
        "@onesever — Владелец\n"
        "@creatorr13 — Модератор\n"
        "@krasnov_hub — Модератор\n"
        "@wrezx — Модератор",
        parse_mode="Markdown"
    )

# ----------------- ПОДАЧА ОБЪЯВЛЕНИЯ -----------------

@dp.message_handler(text="📢 Опубликовать объявление")
async def start_post(message: types.Message):
    await message.answer(
        "✍️ *Отправьте текст объявления*\n\n"
        "Пример:\n"
        "1) Продам: Дом в Бусаево\n"
        "2) Цена: 11.000.000\n"
        "3) Связь: @username\n\n"
        "_Фото добавите на следующем шаге_",
        parse_mode="Markdown"
    )

@dp.message_handler(content_types=types.ContentType.TEXT)
async def receive_text(message: types.Message):
    if message.text.startswith("/"):
        return

    data = load_data()
    uid = str(message.from_user.id)

    last = data["last_post_time"].get(uid, 0)
    if time.time() - last < 7200:
        await message.answer("⏳ Вы можете подавать объявление раз в 2 часа.")
        return

    data["counter"] += 1
    post_id = str(data["counter"])

    data["posts"][post_id] = {
        "user_id": message.from_user.id,
        "username": message.from_user.username,
        "name": message.from_user.full_name,
        "text": message.text,
        "photos": [],
        "status": "draft"
    }

    save_data(data)

    await message.answer(
        "📸 Теперь отправьте фото (можно несколько)\n"
        "Или напишите *Готово*, если без фото",
        parse_mode="Markdown"
    )

@dp.message_handler(content_types=types.ContentType.PHOTO)
async def receive_photo(message: types.Message):
    data = load_data()
    post_id = list(data["posts"].keys())[-1]
    data["posts"][post_id]["photos"].append(message.photo[-1].file_id)
    save_data(data)

@dp.message_handler(text="Готово")
async def preview(message: types.Message):
    data = load_data()
    post_id = list(data["posts"].keys())[-1]
    post = data["posts"][post_id]

    text = (
        f"📝 *Предпросмотр*\n\n"
        f"{post['text']}\n\n"
        "_Подтвердите или отмените_"
    )

    if post["photos"]:
        await bot.send_media_group(
            message.chat.id,
            [types.InputMediaPhoto(p) for p in post["photos"]]
        )

    await message.answer(text, reply_markup=confirm_kb(), parse_mode="Markdown")

# ----------------- ПОДТВЕРЖДЕНИЕ -----------------

@dp.callback_query_handler(text="confirm_post")
async def send_to_moderation(call: types.CallbackQuery):
    data = load_data()
    post_id = list(data["posts"].keys())[-1]
    post = data["posts"][post_id]
    post["status"] = "pending"
    data["last_post_time"][str(post["user_id"])] = time.time()
    save_data(data)

    for admin in ADMIN_IDS:
        text = (
            f"🆕 Объявление №{post_id}\n"
            f"👤 {post['name']} (@{post['username']})\n"
            f"ID: {post['user_id']}\n\n"
            f"{post['text']}"
        )

        if post["photos"]:
            await bot.send_media_group(
                admin,
                [types.InputMediaPhoto(p) for p in post["photos"]]
            )

        await bot.send_message(admin, text, reply_markup=moderation_kb(post_id))

    await call.message.answer("✅ Объявление отправлено на модерацию!")
    await call.answer()

@dp.callback_query_handler(text="cancel_post")
async def cancel(call: types.CallbackQuery):
    await call.message.answer("❌ Подача объявления отменена")
    await call.answer()

# ----------------- МОДЕРАЦИЯ -----------------

@dp.callback_query_handler(lambda c: c.data.startswith(("approve", "reject")))
async def moderate(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return

    action, post_id = call.data.split(":")
    data = load_data()
    post = data["posts"].get(post_id)

    if not post or post["status"] != "pending":
        await call.answer("⚠️ Уже обработано", show_alert=True)
        return

    post["status"] = action
    save_data(data)

    for admin in ADMIN_IDS:
        await bot.send_message(
            admin,
            f"📌 Объявление №{post_id}\n"
            f"{'✅ Одобрено' if action == 'approve' else '❌ Отклонено'}\n"
            f"Модератор: {call.from_user.full_name}"
        )

    if action == "approve":
        if post["photos"]:
            await bot.send_media_group(
                CHANNEL_ID,
                [types.InputMediaPhoto(p) for p in post["photos"]]
            )
        await bot.send_message(CHANNEL_ID, post["text"])
        await bot.send_message(post["user_id"], "✅ Ваше объявление опубликовано!")
    else:
        await bot.send_message(post["user_id"], "❌ Ваше объявление отклонено")

    await call.answer()

# ----------------- РАССЫЛКА -----------------

@dp.message_handler(commands=["broadcast"])
async def broadcast(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    text = message.get_args()
    if not text:
        await message.answer("Использование:\n/broadcast ТЕКСТ")
        return

    data = load_data()
    sent = failed = 0

    for uid in data["users"]:
        try:
            await bot.send_message(uid, text)
            sent += 1
            await asyncio.sleep(0.05)
        except:
            failed += 1

    await message.answer(f"📣 Рассылка завершена\n\n✅ {sent}\n❌ {failed}")

# ----------------- USERS -----------------

@dp.message_handler(commands=["users"])
async def users_count(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    data = load_data()
    await message.answer(f"👥 Пользователей: {len(data['users'])}")

# ----------------- ЗАПУСК -----------------

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
