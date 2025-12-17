import logging
import time
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto
)

# ================== НАСТРОЙКИ ==================

TOKEN = "8514017811:AAGITL2iFpWYWvJu7EACrW_EzCYD9oUlUMc"
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
dp = Dispatcher(bot, storage=MemoryStorage())

# ================== ХРАНЕНИЕ ==================

last_post_time = {}      # user_id -> timestamp
pending_ads = {}         # ad_id -> data
processed_ads = {}       # ad_id -> moderator_id
ad_counter = 0

# ================== FSM ==================

class AdForm(StatesGroup):
    text = State()
    ask_photo = State()
    photos = State()
    confirm = State()

# ================== ВСПОМОГАТЕЛЬНОЕ ==================

def format_time(seconds: int) -> str:
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours > 0:
        return f"{hours} ч {minutes} мин"
    return f"{minutes} мин"

# ================== КЛАВИАТУРЫ ==================

main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
main_kb.add("📢 Опубликовать объявление")
main_kb.add("📖 Помощь", "📞 Связь с владельцем")
main_kb.add("👮 Модераторы")

ask_photo_kb = ReplyKeyboardMarkup(resize_keyboard=True)
ask_photo_kb.add("➕ Добавить фото", "➡️ Без фото")

photo_done_kb = ReplyKeyboardMarkup(resize_keyboard=True)
photo_done_kb.add("✅ Готово")

confirm_kb = InlineKeyboardMarkup()
confirm_kb.add(
    InlineKeyboardButton("✅ Подтвердить", callback_data="confirm"),
    InlineKeyboardButton("❌ Отменить", callback_data="cancel")
)

def moderation_kb(ad_id: int):
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("✅ Одобрить", callback_data=f"approve:{ad_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject:{ad_id}")
    )
    return kb

# ================== START ==================

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer(
        "👋 Добро пожаловать!\n\n"
        "Здесь вы можете подать объявление для публикации.\n"
        "Все объявления проходят модерацию.",
        reply_markup=main_kb
    )

# ================== ИНФО ==================

@dp.message_handler(text="📖 Помощь")
async def help_msg(message: types.Message):
    await message.answer(
        "📌 <b>Как подать объявление</b>\n\n"
        "1️⃣ Нажмите «Опубликовать объявление»\n"
        "2️⃣ Отправьте текст\n"
        "3️⃣ Выберите: с фото или без\n"
        "4️⃣ Проверьте предпросмотр\n"
        "5️⃣ Подтвердите\n\n"
        "⏳ Ограничение: 1 объявление раз в 2 часа"
    )

@dp.message_handler(text="📞 Связь с владельцем")
async def owner(message: types.Message):
    await message.answer(f"👑 Владелец: {OWNER_USERNAME}")

@dp.message_handler(text="👮 Модераторы")
async def mods_list(message: types.Message):
    await message.answer(
        "👮 <b>Модераторы проекта</b>\n\n"
        "👑 Владелец:\n• @onesever\n\n"
        "🛡 Модераторы:\n"
        "• @creatorr13\n"
        "• @krasnov_hub\n"
        "• @wrezx"
    )

# ================== ПОДАЧА ==================

@dp.message_handler(text="📢 Опубликовать объявление")
async def start_ad(message: types.Message):
    uid = message.from_user.id
    now = time.time()

    if uid in last_post_time:
        diff = int(now - last_post_time[uid])
        if diff < ANTISPAM_SECONDS:
            left = ANTISPAM_SECONDS - diff
            await message.answer(
                f"⏳ Вы уже отправляли объявление.\n"
                f"Попробуйте снова через {format_time(left)}"
            )
            return

    await message.answer(
        "✍️ <b>Отправьте текст объявления</b>\n\n"
        "Пример:\n"
        "1) Продам: Дом в Бусаево\n"
        "2) Цена: 11.000.000\n"
        "3) Связь: @username\n\n"
        "<i>Фото добавляются на следующем шаге</i>",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await AdForm.text.set()

@dp.message_handler(state=AdForm.text, content_types=types.ContentTypes.TEXT)
async def get_text(message: types.Message, state: FSMContext):
    await state.update_data(text=message.text, photos=[])
    await message.answer(
        "📸 Хотите добавить фото к объявлению?",
        reply_markup=ask_photo_kb
    )
    await AdForm.ask_photo.set()

@dp.message_handler(state=AdForm.ask_photo, text="➡️ Без фото")
async def no_photo(message: types.Message, state: FSMContext):
    await show_preview(message, state)

@dp.message_handler(state=AdForm.ask_photo, text="➕ Добавить фото")
async def add_photo(message: types.Message, state: FSMContext):
    await message.answer(
        "📸 Отправьте фото (можно несколько)\n"
        "Когда закончите — нажмите «Готово»",
        reply_markup=photo_done_kb
    )
    await AdForm.photos.set()

@dp.message_handler(state=AdForm.photos, content_types=types.ContentTypes.PHOTO)
async def get_photos(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    photos.append(message.photo[-1].file_id)
    await state.update_data(photos=photos)

@dp.message_handler(state=AdForm.photos, text="✅ Готово")
async def finish_photos(message: types.Message, state: FSMContext):
    await show_preview(message, state)

# ================== ПРЕДПРОСМОТР ==================

async def show_preview(message: types.Message, state: FSMContext):
    data = await state.get_data()
    text = data["text"]
    photos = data.get("photos", [])

    await message.answer(
        "🔍 <b>Предпросмотр объявления</b>",
        reply_markup=types.ReplyKeyboardRemove()
    )

    if photos:
        media = [InputMediaPhoto(photos[0], caption=text)]
        for p in photos[1:]:
            media.append(InputMediaPhoto(p))
        await bot.send_media_group(message.chat.id, media)
    else:
        await message.answer(text)

    await message.answer(
        "❗ Проверьте объявление.\n"
        "Подтвердите отправку или отмените.",
        reply_markup=confirm_kb
    )
    await AdForm.confirm.set()

# ================== ПОДТВЕРЖДЕНИЕ ==================

@dp.callback_query_handler(text="confirm", state=AdForm.confirm)
async def confirm_send(call: types.CallbackQuery, state: FSMContext):
    global ad_counter
    ad_counter += 1
    ad_id = ad_counter

    data = await state.get_data()
    user = call.from_user

    pending_ads[ad_id] = {
        "user": user,
        "text": data["text"],
        "photos": data.get("photos", [])
    }

    caption = (
        f"🆕 <b>Объявление №{ad_id}</b>\n\n"
        f"👤 {user.full_name} (@{user.username})\n"
        f"🆔 ID: {user.id}\n\n"
        f"{data['text']}"
    )

    for mid in MODERATORS:
        if data["photos"]:
            media = [InputMediaPhoto(data["photos"][0], caption=caption)]
            for p in data["photos"][1:]:
                media.append(InputMediaPhoto(p))
            await bot.send_media_group(mid, media)
            await bot.send_message(mid, "⬆️ Модерация", reply_markup=moderation_kb(ad_id))
        else:
            await bot.send_message(mid, caption, reply_markup=moderation_kb(ad_id))

    last_post_time[user.id] = time.time()
    await state.finish()
    await call.message.answer("✅ Объявление отправлено на модерацию")
    await call.answer()

@dp.callback_query_handler(text="cancel", state=AdForm.confirm)
async def cancel_send(call: types.CallbackQuery, state: FSMContext):
    await state.finish()
    await call.message.answer("❌ Подача объявления отменена")
    await call.answer()

# ================== МОДЕРАЦИЯ ==================

@dp.callback_query_handler(lambda c: c.data.startswith(("approve:", "reject:")))
async def moderate(call: types.CallbackQuery):
    uid = call.from_user.id
    if uid not in MODERATORS:
        await call.answer("Нет прав", show_alert=True)
        return

    action, ad_id_str = call.data.split(":")
    ad_id = int(ad_id_str)

    if ad_id in processed_ads:
        await call.answer(
            f"⚠️ Объявление №{ad_id} уже обработано\n"
            f"👮 Модератор: {processed_ads[ad_id]}",
            show_alert=True
        )
        return

    ad = pending_ads.get(ad_id)
    if not ad:
        await call.answer("Ошибка", show_alert=True)
        return

    processed_ads[ad_id] = call.from_user.full_name

    if action == "approve":
        if ad["photos"]:
            media = [InputMediaPhoto(ad["photos"][0], caption=ad["text"])]
            for p in ad["photos"][1:]:
                media.append(InputMediaPhoto(p))
            await bot.send_media_group(CHANNEL_ID, media)
        else:
            await bot.send_message(CHANNEL_ID, ad["text"])

        await bot.send_message(ad["user"].id, f"✅ Ваше объявление №{ad_id} опубликовано!")
        result = "ОДОБРЕНО"
    else:
        await bot.send_message(ad["user"].id, f"❌ Ваше объявление №{ad_id} отклонено.")
        result = "ОТКЛОНЕНО"

    for mid in MODERATORS:
        await bot.send_message(
            mid,
            f"📌 Объявление №{ad_id} {result}\n"
            f"👮 Модератор: {call.from_user.full_name}"
        )

    await call.message.edit_reply_markup()
    await call.answer("Готово")

# ================== ЗАПУСК ==================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
