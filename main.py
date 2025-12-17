import time
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.utils import executor

# ================== НАСТРОЙКИ ==================

TOKEN = "8514017811:AAEsYCKjAdbjz907KD0O_mY-eKQPEN5iD4Y"
CHANNEL_ID = -1001234567890   # ID канала с -100

OWNER_USERNAME = "@onesever"

# ВСЕ модераторы (включая владельца)
MODERATORS = [
    724545647,     # onesever (владелец)
    8390126598,
    7946280692,
    7244927531,
]

ANTI_SPAM_SECONDS = 2 * 60 * 60  # 2 часа

# ================== INIT ==================

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# ================== FSM ==================

class AdForm(StatesGroup):
    waiting_text = State()
    waiting_photo = State()
    preview = State()

# ================== ХРАНЕНИЕ ==================

last_post_time = {}
pending_ads = {}
ad_counter = 0

# ================== КЛАВИАТУРЫ ==================

main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
main_kb.add("📢 Опубликовать объявление")
main_kb.add("📖 Помощь", "📞 Связь с владельцем")
main_kb.add("👥 Модераторы")

def preview_kb(ad_id):
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm:{ad_id}"),
        InlineKeyboardButton("❌ Отменить", callback_data=f"cancel:{ad_id}")
    )
    return kb

def moderation_kb(ad_id):
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("✅ Одобрить", callback_data=f"approve:{ad_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject:{ad_id}")
    )
    return kb

# ================== /start ==================

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer(
        "👋 Добро пожаловать!\n\n"
        "Здесь вы можете подать объявление для публикации.\n"
        "Все объявления проходят модерацию.",
        reply_markup=main_kb
    )

# ================== КНОПКИ ==================

@dp.message_handler(text="📖 Помощь")
async def help_msg(message: types.Message):
    await message.answer(
        "📌 *Как подать объявление*\n\n"
        "1️⃣ Нажмите «Опубликовать объявление»\n"
        "2️⃣ Отправьте ТЕКСТ\n"
        "3️⃣ Добавьте ФОТО или напишите *Готово*\n"
        "4️⃣ Проверьте предпросмотр\n"
        "5️⃣ Подтвердите\n\n"
        "⏳ Антиспам: 1 объявление раз в 2 часа",
        parse_mode="Markdown"
    )

@dp.message_handler(text="📞 Связь с владельцем")
async def owner_contact(message: types.Message):
    await message.answer(f"👑 Владелец: {OWNER_USERNAME}")

@dp.message_handler(text="👥 Модераторы")
async def moderators_list(message: types.Message):
    await message.answer(
        "👥 *Модераторы проекта:*\n\n"
        "@onesever — Владелец\n"
        "@creatorr13 — Модератор\n"
        "@krasnov_hub — Модератор\n"
        "@wrezx — Модератор",
        parse_mode="Markdown"
    )

# ================== ПОДАЧА ОБЪЯВЛЕНИЯ ==================

@dp.message_handler(text="📢 Опубликовать объявление")
async def start_ad(message: types.Message):
    uid = message.from_user.id
    now = time.time()

    if uid in last_post_time and now - last_post_time[uid] < ANTI_SPAM_SECONDS:
        await message.answer("⏳ Вы можете отправлять объявление раз в 2 часа.")
        return

    await AdForm.waiting_text.set()
    await message.answer(
        "✍️ *Отправьте текст объявления*\n\n"
        "Пример:\n"
        "1) Продам: Дом в Бусаево\n"
        "2) Цена: 11.000.000\n"
        "3) Связь: @username\n\n"
        "_Фото добавляется на следующем шаге_",
        parse_mode="Markdown"
    )

@dp.message_handler(state=AdForm.waiting_text, content_types=types.ContentTypes.TEXT)
async def get_text(message: types.Message, state: FSMContext):
    await state.update_data(text=message.text, photos=[])
    await AdForm.waiting_photo.set()
    await message.answer(
        "📸 Теперь отправьте фото (можно несколько)\n"
        "Или напишите *Готово*, если без фото",
        parse_mode="Markdown"
    )

@dp.message_handler(state=AdForm.waiting_photo, content_types=types.ContentTypes.PHOTO)
async def get_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    photos.append(message.photo[-1].file_id)
    await state.update_data(photos=photos)

@dp.message_handler(state=AdForm.waiting_photo, content_types=types.ContentTypes.TEXT)
async def finish_photos(message: types.Message, state: FSMContext):
    if message.text.lower() != "готово":
        return

    global ad_counter
    ad_counter += 1
    ad_id = ad_counter

    data = await state.get_data()

    pending_ads[ad_id] = {
        "user": message.from_user,
        "text": data["text"],
        "photos": data["photos"],
        "status": "pending"
    }

    preview_text = f"📝 *Предпросмотр объявления №{ad_id}*\n\n{data['text']}"

    if data["photos"]:
        await message.answer_photo(
            data["photos"][0],
            caption=preview_text,
            reply_markup=preview_kb(ad_id),
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            preview_text,
            reply_markup=preview_kb(ad_id),
            parse_mode="Markdown"
        )

    await AdForm.preview.set()

# ================== ПОДТВЕРЖДЕНИЕ ==================

@dp.callback_query_handler(lambda c: c.data.startswith("confirm:"))
async def confirm_post(call: types.CallbackQuery, state: FSMContext):
    ad_id = int(call.data.split(":")[1])
    ad = pending_ads.get(ad_id)

    if not ad:
        await call.answer("Ошибка")
        return

    text = (
        f"🆕 *Объявление №{ad_id}*\n\n"
        f"{ad['text']}\n\n"
        f"👤 От: {ad['user'].full_name} "
        f"(@{ad['user'].username or 'без_юзера'})\n"
        f"ID: {ad['user'].id}"
    )

    for mod in MODERATORS:
        if ad["photos"]:
            await bot.send_photo(
                mod,
                ad["photos"][0],
                caption=text,
                reply_markup=moderation_kb(ad_id),
                parse_mode="Markdown"
            )
        else:
            await bot.send_message(
                mod,
                text,
                reply_markup=moderation_kb(ad_id),
                parse_mode="Markdown"
            )

    last_post_time[ad["user"].id] = time.time()
    await call.message.edit_reply_markup()
    await call.message.answer("✅ Объявление отправлено на модерацию")
    await state.finish()
    await call.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("cancel:"))
async def cancel_post(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("❌ Подача объявления отменена")
    await state.finish()
    await call.answer()

# ================== МОДЕРАЦИЯ ==================

@dp.callback_query_handler(lambda c: c.data.startswith(("approve:", "reject:")))
async def moderate(call: types.CallbackQuery):
    if call.from_user.id not in MODERATORS:
        await call.answer("Нет прав")
        return

    action, ad_id = call.data.split(":")
    ad_id = int(ad_id)
    ad = pending_ads.get(ad_id)

    if not ad or ad["status"] != "pending":
        await call.answer("⚠️ Уже обработано", show_alert=True)
        return

    ad["status"] = action

    result_text = (
        f"📌 Объявление №{ad_id}\n"
        f"{'✅ Одобрено' if action == 'approve' else '❌ Отклонено'}\n"
        f"👮 Модератор: {call.from_user.full_name}"
    )

    for mod in MODERATORS:
        await bot.send_message(mod, result_text)

    if action == "approve":
        if ad["photos"]:
            await bot.send_photo(CHANNEL_ID, ad["photos"][0], caption=ad["text"])
        else:
            await bot.send_message(CHANNEL_ID, ad["text"])

        await bot.send_message(ad["user"].id, "✅ Ваше объявление опубликовано!")
    else:
        await bot.send_message(ad["user"].id, "❌ Ваше объявление отклонено.")

    await call.message.edit_reply_markup()
    await call.answer("Готово")

# ================== ЗАПУСК ==================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
