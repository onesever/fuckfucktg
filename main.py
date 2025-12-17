import asyncio
import json
import time
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto
)

# ================== НАСТРОЙКИ ==================

TOKEN = "8514017811:AAF-YaBx_1ji6TJ70Q7UkYw77A2-t4a9C8w"
CHANNEL_ID = "@blackrussia_85"

ADMIN_IDS = [
    724545647,
    8390126598,
    7946280692,
    7244927531
]

ANTISPAM_SECONDS = 2 * 60 * 60
DATA_FILE = "data.json"

bot = Bot(TOKEN)
dp = Dispatcher()
LOCK = asyncio.Lock()

# ================== ХРАНЕНИЕ ==================

def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {
            "posts": {},
            "last_post_time": {},
            "counter": 0,
            "users": []
        }

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ================== КЛАВИАТУРА ==================

user_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📢 Опубликовать объявление")],
        [KeyboardButton(text="👮‍♂️ Модераторы")],
        [KeyboardButton(text="📖 Помощь"), KeyboardButton(text="📞 Связь с владельцем")]
    ],
    resize_keyboard=True
)

# ================== /start ==================

@dp.message(Command("start"))
async def start(message: types.Message):
    data = load_data()
    uid = str(message.from_user.id)
    if uid not in data["users"]:
        data["users"].append(uid)
        save_data(data)

    await message.answer(
        "👋 Добро пожаловать!\n\n"
        "Здесь вы можете подать объявление.\n"
        "Все объявления проходят модерацию.",
        reply_markup=user_kb
    )

# ================== ИНФО ==================

@dp.message(F.text == "📞 Связь с владельцем")
async def contact_owner(message: types.Message):
    await message.answer("📬 Связь с владельцем: @onesever")

@dp.message(F.text == "👮‍♂️ Модераторы")
async def moderators(message: types.Message):
    await message.answer(
        "👮‍♂️ *Модераторы канала:*\n\n"
        "@onesever — Владелец\n"
        "@creatorr13 — Модератор\n"
        "@krasnov_hub — Модератор\n"
        "@wrezx — Модератор",
        parse_mode="Markdown"
    )

@dp.message(F.text == "📖 Помощь")
async def help_msg(message: types.Message):
    await message.answer(
        "📘 *Как подать объявление:*\n\n"
        "1️⃣ Нажмите «Опубликовать объявление»\n"
        "2️⃣ Отправьте текст объявления\n"
        "3️⃣ Добавьте фото (по желанию)\n"
        "4️⃣ Подтвердите отправку\n\n"
        "⏳ Ограничение: 1 объявление в 2 часа",
        parse_mode="Markdown"
    )

# ================== СОСТОЯНИЯ ==================

user_states = {}

# ================== ПОДАЧА ==================

@dp.message(F.text == "📢 Опубликовать объявление")
async def start_post(message: types.Message):
    data = load_data()
    last = data["last_post_time"].get(str(message.from_user.id), 0)

    if time.time() - last < ANTISPAM_SECONDS:
        await message.answer("⏳ Можно отправлять объявление раз в 2 часа.")
        return

    user_states[message.from_user.id] = {"text": None, "photos": []}

    await message.answer(
        "✏️ *Отправьте текст объявления*\n\n"
        "Пример:\n"
        "1) Продам: Дом в Бусаево\n"
        "2) Цена: 11.000.000\n"
        "3) Связь: @username\n\n"
        "❗ Фото сейчас НЕ отправляйте",
        parse_mode="Markdown"
    )

@dp.message(F.text)
async def receive_text(message: types.Message):
    state = user_states.get(message.from_user.id)
    if not state or state["text"]:
        return

    state["text"] = message.text

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📷 Добавить фото", callback_data="add_photo")],
        [InlineKeyboardButton(text="➡️ Без фото", callback_data="no_photo")]
    ])

    await message.answer("Теперь добавьте фото или нажмите «Без фото»", reply_markup=kb)

@dp.callback_query(F.data.in_(["add_photo", "no_photo"]))
async def photo_choice(call: types.CallbackQuery):
    await call.answer()
    if call.data == "no_photo":
        await preview(call.from_user.id, call.message)
    else:
        await call.message.answer(
            "📸 Отправляйте фото (можно несколько).\n"
            "Когда закончите — нажмите «Готово»"
        )

@dp.message(F.photo)
async def collect_photo(message: types.Message):
    state = user_states.get(message.from_user.id)
    if not state or not state["text"]:
        return

    state["photos"].append(message.photo[-1].file_id)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✅ Готово", callback_data="finish_photos")]]
    )
    await message.answer("Фото добавлено", reply_markup=kb)

@dp.callback_query(F.data == "finish_photos")
async def finish_photos(call: types.CallbackQuery):
    await call.answer()
    await preview(call.from_user.id, call.message)

# ================== ПРЕДПРОСМОТР ==================

async def preview(user_id, message):
    state = user_states[user_id]

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel")]
    ])

    if state["photos"]:
        media = [InputMediaPhoto(media=state["photos"][0], caption=state["text"])]
        for p in state["photos"][1:]:
            media.append(InputMediaPhoto(media=p))
        await message.answer_media_group(media)
        await message.answer("Проверьте объявление 👇", reply_markup=kb)
    else:
        await message.answer(
            f"👀 *Предпросмотр:*\n\n{state['text']}",
            parse_mode="Markdown",
            reply_markup=kb
        )

# ================== ПОДТВЕРЖДЕНИЕ ==================

@dp.callback_query(F.data.in_(["confirm", "cancel"]))
async def confirm_post(call: types.CallbackQuery):
    await call.answer()
    if call.data == "cancel":
        user_states.pop(call.from_user.id, None)
        await call.message.answer("❌ Отменено", reply_markup=user_kb)
        return

    async with LOCK:
        data = load_data()
        data["counter"] += 1
        number = data["counter"]

        post = user_states.pop(call.from_user.id)
        post.update({
            "id": number,
            "from_id": call.from_user.id,
            "username": call.from_user.username,
            "status": "pending"
        })

        data["posts"][str(number)] = post
        data["last_post_time"][str(call.from_user.id)] = time.time()
        save_data(data)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve:{number}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject:{number}")
        ]
    ])

    for admin in ADMIN_IDS:
        if post["photos"]:
            media = [InputMediaPhoto(
                media=post["photos"][0],
                caption=f"📌 Объявление №{number}\n"
                        f"👤 @{post['username']}\n\n{post['text']}"
            )]
            for p in post["photos"][1:]:
                media.append(InputMediaPhoto(media=p))
            await bot.send_media_group(admin, media)
            await bot.send_message(admin, "⬆️ Модерация", reply_markup=kb)
        else:
            await bot.send_message(
                admin,
                f"📌 Объявление №{number}\n"
                f"👤 @{post['username']}\n\n{post['text']}",
                reply_markup=kb
            )

    await call.message.answer("✅ Отправлено на модерацию", reply_markup=user_kb)

# ================== МОДЕРАЦИЯ ==================

@dp.callback_query(F.data.startswith(("approve", "reject")))
async def moderation(call: types.CallbackQuery):
    action, number = call.data.split(":")
    moderator = call.from_user.full_name

    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Нет прав", show_alert=True)
        return

    async with LOCK:
        data = load_data()
        post = data["posts"].get(number)

        if not post or post["status"] != "pending":
            await call.answer("Уже обработано")
            return

        post["status"] = action
        save_data(data)

    if action == "approve":
        if post["photos"]:
            media = [InputMediaPhoto(media=post["photos"][0], caption=post["text"])]
            for p in post["photos"][1:]:
                media.append(InputMediaPhoto(media=p))
            await bot.send_media_group(CHANNEL_ID, media)
        else:
            await bot.send_message(CHANNEL_ID, post["text"])

    await bot.send_message(
        post["from_id"],
        f"{'✅' if action == 'approve' else '❌'} "
        f"Объявление №{number} "
        f"{'опубликовано' if action == 'approve' else 'отклонено'}\n"
        f"👮 Модератор: {moderator}"
    )

    for admin in ADMIN_IDS:
        await bot.send_message(
            admin,
            f"📌 Объявление №{number} обработано\n"
            f"👮 Модератор: {moderator}\n"
            f"📄 Статус: {'Одобрено' if action == 'approve' else 'Отклонено'}"
        )

    await call.message.edit_reply_markup()

# ================== РАССЫЛКА ==================

@dp.message(Command("broadcast"))
async def broadcast(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    text = message.text.replace("/broadcast", "").strip()
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

    await message.answer(
        f"📣 Рассылка завершена\n\n"
        f"✅ Отправлено: {sent}\n"
        f"❌ Ошибок: {failed}"
    )

# ================== ПОЛЬЗОВАТЕЛИ ==================

@dp.message(Command("users"))
async def users_count(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    data = load_data()
    await message.answer(f"👥 Пользователей бота: {len(data['users'])}")

# ================== ЗАПУСК ==================

async def main():
    print("🤖 Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
