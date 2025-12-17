import logging
import time
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto
)
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

API_TOKEN = "8514017811:AAFSDW1z8qyIkY8Mo6GSpttXG1RPKHBvVUc"
CHANNEL_ID = "@blackrussia_85"

# ===== МОДЕРАТОРЫ (4 ЧЕЛОВЕКА) =====
MODERATORS = [
    8390126598,
    7946280692,
    7244927531,
    724545647
]

OWNER_USERNAME = "@onesever"

ANTISPAM_SECONDS = 2 * 60 * 60  # 2 часа

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot, storage=MemoryStorage())

last_post_time = {}
processed_ads = set()
ad_counter = 0

# ===== FSM =====
class AdForm(StatesGroup):
    text = State()
    photos = State()
    confirm = State()

# ===== КНОПКИ =====
main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
main_kb.add("📢 Опубликовать объявление")
main_kb.add("📖 Помощь", "📞 Связь с владельцем")
main_kb.add("👮 Модераторы")

confirm_kb = InlineKeyboardMarkup()
confirm_kb.add(
    InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_send"),
    InlineKeyboardButton("❌ Отменить", callback_data="cancel_send")
)

moder_kb = InlineKeyboardMarkup()
moder_kb.add(
    InlineKeyboardButton("✅ Одобрить", callback_data="approve"),
    InlineKeyboardButton("❌ Отклонить", callback_data="reject")
)

# ===== /start =====
@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer(
        "👋 Добро пожаловать!\n\n"
        "Здесь вы можете подать объявление.\n"
        "Оно будет проверено модераторами.",
        reply_markup=main_kb
    )

# ===== ПОМОЩЬ =====
@dp.message_handler(text="📖 Помощь")
async def help_msg(message: types.Message):
    await message.answer(
        "📌 <b>Как подать объявление</b>\n\n"
        "1️⃣ Нажмите «Опубликовать объявление»\n"
        "2️⃣ Отправьте ТЕКСТ\n"
        "3️⃣ Добавьте ФОТО или напишите <b>Готово</b>\n"
        "4️⃣ Проверьте предпросмотр\n"
        "5️⃣ Подтвердите\n\n"
        "⏳ Антиспам: 1 объявление раз в 2 часа"
    )

# ===== СВЯЗЬ =====
@dp.message_handler(text="📞 Связь с владельцем")
async def owner(message: types.Message):
    await message.answer(f"📬 Владелец проекта: {OWNER_USERNAME}")

# ===== СПИСОК МОДЕРАТОРОВ =====
@dp.message_handler(text="👮 Модераторы")
async def moderators(message: types.Message):
    await message.answer(
        "👮 <b>Модераторы проекта</b>\n\n"
        "👑 Владелец:\n"
        "• @onesever\n\n"
        "🛡 Модераторы:\n"
        "• @creatorr13\n"
        "• @krasnov_hub\n"
        "• @wrezx"
    )

# ===== НАЧАЛО ПОДАЧИ =====
@dp.message_handler(text="📢 Опубликовать объявление")
async def start_ad(message: types.Message):
    uid = message.from_user.id
    now = time.time()

    if uid in last_post_time and now - last_post_time[uid] < ANTISPAM_SECONDS:
        await message.answer("⏳ Вы уже отправляли объявление. Попробуйте позже.")
        return

    await message.answer(
        "✏️ <b>Отправьте текст объявления</b>\n\n"
        "Пример:\n"
        "1) Продам: Дом в Бусаево\n"
        "2) Цена: 11.000.000\n"
        "3) Связь: @username\n\n"
        "<i>Фото добавляется на следующем шаге</i>"
    )
    await AdForm.text.set()

# ===== ПОЛУЧЕНИЕ ТЕКСТА =====
@dp.message_handler(state=AdForm.text, content_types=types.ContentTypes.TEXT)
async def get_text(message: types.Message, state: FSMContext):
    await state.update_data(text=message.text, photos=[])
    await message.answer(
        "📸 Теперь отправьте фото (можно несколько)\n"
        "Или напишите <b>Готово</b>, если без фото"
    )
    await AdForm.photos.set()

# ===== ПОЛУЧЕНИЕ ФОТО =====
@dp.message_handler(content_types=types.ContentTypes.PHOTO, state=AdForm.photos)
async def get_photos(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    photos.append(message.photo[-1].file_id)
    await state.update_data(photos=photos)

# ===== ГОТОВО =====
@dp.message_handler(state=AdForm.photos, text="Готово")
async def preview(message: types.Message, state: FSMContext):
    data = await state.get_data()
    text = data["text"]
    photos = data["photos"]

    await message.answer("🔍 <b>Предпросмотр объявления</b>")

    if photos:
        media = [InputMediaPhoto(photos[0], caption=text)]
        for p in photos[1:]:
            media.append(InputMediaPhoto(p))
        await bot.send_media_group(message.chat.id, media)
    else:
        await message.answer(text)

    await message.answer(
        "❗ Проверьте объявление\n"
        "Подтвердите или отмените",
        reply_markup=confirm_kb
    )
    await AdForm.confirm.set()

# ===== ПОДТВЕРЖДЕНИЕ =====
@dp.callback_query_handler(lambda c: c.data == "confirm_send", state=AdForm.confirm)
async def send_to_mods(call: types.CallbackQuery, state: FSMContext):
    global ad_counter
    ad_counter += 1

    data = await state.get_data()
    text = data["text"]
    photos = data["photos"]
    user = call.from_user

    caption = (
        f"🆕 <b>Объявление №{ad_counter}</b>\n"
        f"👤 {user.full_name} (@{user.username})\n"
        f"🆔 ID: {user.id}\n\n"
        f"📄 <b>Текст:</b>\n{text}"
    )

    for mid in MODERATORS:
        if photos:
            media = [InputMediaPhoto(photos[0], caption=caption)]
            for p in photos[1:]:
                media.append(InputMediaPhoto(p))
            await bot.send_media_group(mid, media)
            await bot.send_message(mid, "⬆️ Модерация", reply_markup=moder_kb)
        else:
            await bot.send_message(mid, caption, reply_markup=moder_kb)

    last_post_time[user.id] = time.time()
    await state.finish()
    await call.message.answer("✅ Объявление отправлено на модерацию")
    await call.answer()

# ===== ОТМЕНА =====
@dp.callback_query_handler(lambda c: c.data == "cancel_send", state=AdForm.confirm)
async def cancel(call: types.CallbackQuery, state: FSMContext):
    await state.finish()
    await call.message.answer("❌ Подача объявления отменена")
    await call.answer()

# ===== МОДЕРАЦИЯ =====
@dp.callback_query_handler(lambda c: c.data in ["approve", "reject"])
async def moderate(call: types.CallbackQuery):
    if call.from_user.id not in MODERATORS:
        await call.answer("Нет доступа", show_alert=True)
        return

    key = (call.message.chat.id, call.message.message_id)
    if key in processed_ads:
        await call.answer("Уже обработано")
        return

    processed_ads.add(key)

    if call.data == "approve":
        await call.message.copy_to(CHANNEL_ID)
        await call.answer("✅ Опубликовано")
        for mid in MODERATORS:
            await bot.send_message(mid, f"✅ Объявление одобрил {call.from_user.full_name}")
    else:
        await call.answer("❌ Отклонено")
        for mid in MODERATORS:
            await bot.send_message(mid, f"❌ Объявление отклонил {call.from_user.full_name}")

    await call.message.edit_reply_markup()

# ===== ЗАПУСК =====
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
