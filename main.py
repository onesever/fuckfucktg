import logging
import time
import asyncio
import sqlite3
import os
from contextlib import closing
from datetime import datetime

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
    1925510202,
    5743211958,
    6621231808,
]

MAX_PHOTOS = 5

# Текст подписи в конце каждого объявления (кликабельный)
SUBSCRIPTION_TEXT = "\n\n📢 <b>Подпишись на канал:</b> <a href='{}'>Б/У рынок IZHEVSK</a>".format(CHANNEL_LINK)

# Уровни (в секундах)
COOLDOWN_NEWBIE = 2 * 60 * 60 + 30 * 60      # 2ч 30м
COOLDOWN_ACTIVE = 1 * 60 * 60 + 30 * 60     # 1ч 30м
COOLDOWN_TOP = 30 * 60                      # 30м

# ================= ПУТИ К БАЗЕ ДАННЫХ =================

# Определяем путь к папке с данными (БЕЗОПАСНОЕ МЕСТО)
DATA_DIR = "/app/data"
DB_PATH = os.path.join(DATA_DIR, "database.db")

# Создаем папку для данных, если её нет
os.makedirs(DATA_DIR, exist_ok=True)

# ================= INIT =================

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN, parse_mode="HTML")
dp = Dispatcher(bot, storage=MemoryStorage())

# ================= DATABASE =================

def init_db():
    """Инициализация базы данных"""
    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            cursor = conn.cursor()
            
            # Таблица пользователей
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                referrals INTEGER DEFAULT 0,
                invited_by INTEGER,
                last_ad_time INTEGER DEFAULT 0
            )
            """)
            
            # Таблица объявлений
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS ads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                status TEXT DEFAULT 'pending',
                created_at INTEGER DEFAULT (strftime('%s', 'now'))
            )
            """)
            
            conn.commit()
            logging.info(f"База данных инициализирована: {DB_PATH}")
    except Exception as e:
        logging.error(f"Ошибка инициализации БД: {e}")

# Инициализируем БД при запуске
init_db()

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

def get_main_keyboard():
    """Создание главной клавиатуры"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("📢 Опубликовать объявление")
    keyboard.add("🎁 Рефералы")
    keyboard.add("📖 Помощь", "📞 Связь с владельцем")
    keyboard.add("👮 Модераторы")
    return keyboard

main_kb = get_main_keyboard()

def get_subscribe_keyboard():
    """Клавиатура для проверки подписки"""
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("📢 Подписаться", url=CHANNEL_LINK),
        InlineKeyboardButton("✅ Я подписался", callback_data="check_sub")
    )
    return keyboard

subscribe_kb = get_subscribe_keyboard()

ask_photo_kb = ReplyKeyboardMarkup(resize_keyboard=True)
ask_photo_kb.add("➕ Добавить фото", "➡️ Без фото")

photo_done_kb = ReplyKeyboardMarkup(resize_keyboard=True)
photo_done_kb.add("✅ Готово")

def get_confirm_keyboard():
    """Клавиатура подтверждения"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("✅ Подтвердить", callback_data="confirm"),
        InlineKeyboardButton("❌ Отменить", callback_data="cancel")
    )
    return keyboard

confirm_kb = get_confirm_keyboard()

def get_moderation_keyboard(ad_id):
    """Клавиатура для модерации"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("✅ Одобрить", callback_data=f"approve:{ad_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject:{ad_id}")
    )
    return keyboard

# ================= УТИЛИТЫ =================

def get_cursor():
    """Получение курсора базы данных"""
    conn = sqlite3.connect(DB_PATH)
    return conn, conn.cursor()

def format_time(seconds):
    """Форматирование времени в читаемый вид"""
    if seconds < 60:
        return f"{seconds} сек"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} мин"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        if minutes > 0:
            return f"{hours}ч {minutes}м"
        else:
            return f"{hours}ч"

def get_level(refs):
    """Получение уровня пользователя по количеству рефералов"""
    if refs >= 100:
        return "🏆 ТОП СЕЛЛЕР", COOLDOWN_TOP
    elif refs >= 30:
        return "🔥 АКТИВНЫЙ СЕЛЛЕР", COOLDOWN_ACTIVE
    else:
        return "👤 НОВИЧОК", COOLDOWN_NEWBIE

def get_level_display(refs):
    """Получение уровня для отображения (с эмодзи)"""
    level, _ = get_level(refs)
    return level

def get_cooldown(refs):
    """Получение времени КД для пользователя"""
    _, cooldown = get_level(refs)
    return cooldown

def can_post(user_id, refs, last_ad_time):
    """Проверка, может ли пользователь опубликовать объявление"""
    now = int(time.time())
    cooldown = get_cooldown(refs)
    
    if last_ad_time == 0:
        return True, 0
    
    time_passed = now - last_ad_time
    
    if time_passed >= cooldown:
        return True, 0
    else:
        remaining = cooldown - time_passed
        return False, remaining

async def check_subscription(user_id):
    """Проверка подписки на канал"""
    try:
        member = await bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logging.error(f"Ошибка проверки подписки: {e}")
        return False

def add_subscription_text(text):
    """Добавляет текст с подпиской на канал в конец сообщения"""
    return text + SUBSCRIPTION_TEXT

# ================= START =================

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    args = message.get_args()
    user_id = message.from_user.id
    
    conn, cursor = get_cursor()
    
    # Проверяем существование пользователя
    cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    user = cursor.fetchone()
    
    if not user:
        invited_by = None
        if args.isdigit() and int(args) != user_id:
            invited_by = int(args)
        
        cursor.execute(
            "INSERT INTO users (user_id, invited_by) VALUES (?, ?)",
            (user_id, invited_by)
        )
        conn.commit()
    
    conn.close()
    
    # Проверка подписки
    if not await check_subscription(user_id):
        await message.answer(
            "❌ Для использования бота подпишитесь на канал:",
            reply_markup=subscribe_kb
        )
        return
    
    await message.answer(
        "👋 Добро пожаловать в бот Б/У рынка IZHEVSK!\n\n"
        "Здесь вы можете публиковать свои объявления.",
        reply_markup=main_kb
    )

@dp.callback_query_handler(lambda c: c.data == "check_sub")
async def check_sub_callback(call: types.CallbackQuery):
    user_id = call.from_user.id
    
    if not await check_subscription(user_id):
        await call.answer("❌ Вы ещё не подписались на канал!", show_alert=True)
        return
    
    conn, cursor = get_cursor()
    
    # Начисляем реферала пригласившему
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
    
    conn.close()
    
    await call.message.delete()
    await call.message.answer(
        "✅ Подписка подтверждена! Теперь вы можете пользоваться ботом.",
        reply_markup=main_kb
    )

# ================= ИНФО =================

@dp.message_handler(lambda m: m.text == "📖 Помощь")
async def help_command(message: types.Message):
    await message.answer(
        "📌 <b>Как подать объявление</b>\n\n"
        "1️⃣ Нажмите кнопку «Опубликовать объявление»\n"
        "2️⃣ Отправьте текст объявления\n"
        "3️⃣ Добавьте фото (до 5 штук, по желанию)\n"
        "4️⃣ Подтвердите отправку\n\n"
        "⚠️ <b>Важно:</b>\n"
        "• В тексте обязательно должен быть указан ваш @username\n"
        "• Время между публикациями зависит от вашего уровня\n"
        "• Объявления проходят модерацию\n\n"
        "❓ Дополнительные вопросы: @onesever",
        reply_markup=main_kb
    )

@dp.message_handler(lambda m: m.text == "📞 Связь с владельцем")
async def owner_contact(message: types.Message):
    await message.answer(
        "👑 <b>Владелец бота:</b> @onesever\n\n"
        "По всем вопросам обращайтесь к нему.",
        reply_markup=main_kb
    )

@dp.message_handler(lambda m: m.text == "👮 Модераторы")
async def moderators_list(message: types.Message):
    await message.answer(
        "👮 <b>Команда модераторов:</b>\n\n"
        "👑 @onesever - Главный модератор\n"
        "🛡️ @creatorr13\n"
        "🛡️ @wrezx\n"
        "🛡️ @qwixx_am\n"
        "🛡️ @Bob1na\n"
        "🛡️ @MensClub4\n\n"
        "Обращайтесь к ним по вопросам модерации.",
        reply_markup=main_kb
    )

# ================= ПОДАЧА ОБЪЯВЛЕНИЯ =================

@dp.message_handler(lambda m: m.text == "📢 Опубликовать объявление")
async def create_ad(message: types.Message):
    user_id = message.from_user.id
    
    # Проверка подписки
    if not await check_subscription(user_id):
        await message.answer(
            "❌ Для публикации объявлений нужно быть подписанным на канал.",
            reply_markup=subscribe_kb
        )
        return
    
    conn, cursor = get_cursor()
    cursor.execute("SELECT referrals, last_ad_time FROM users WHERE user_id=?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        # Если пользователя нет в БД
        conn, cursor = get_cursor()
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        conn.close()
        refs, last_ad_time = 0, 0
    else:
        refs, last_ad_time = result
    
    # Проверяем возможность публикации
    can_post_now, remaining = can_post(user_id, refs, last_ad_time)
    
    if not can_post_now:
        level_name = get_level_display(refs)
        await message.answer(
            f"⏳ <b>КД активен!</b>\n\n"
            f"Ваш уровень: {level_name}\n"
            f"Осталось подождать: {format_time(remaining)}\n\n"
            f"Следующая публикация будет доступна через {format_time(remaining)}"
        )
        return
    
    # Показываем информацию о текущем уровне
    level_name = get_level_display(refs)
    cooldown = get_cooldown(refs)
    
    await message.answer(
        f"✍️ <b>Введите текст объявления</b>\n\n"
        f"📊 <b>Ваш статус:</b> {level_name}\n"
        f"⏱ <b>КД:</b> {format_time(cooldown)}\n\n"
        f"📌 <b>Пример оформления:</b>\n"
        f"Продам дом в Бусаево\n"
        f"Цена: 17кк\n"
        f"Связь: @username\n\n"
        f"⚠️ <b>Обязательно укажите ваш @username в тексте!</b>",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await AdForm.text.set()

@dp.message_handler(state=AdForm.text)
async def process_ad_text(message: types.Message, state: FSMContext):
    # Проверка наличия username
    if not message.from_user.username:
        await message.answer(
            "❌ У вас не установлен username в Telegram.\n"
            "Пожалуйста, установите его в настройках и попробуйте снова.",
            reply_markup=main_kb
        )
        await state.finish()
        return
    
    # Проверка наличия username в тексте
    user_mention = f"@{message.from_user.username}"
    if user_mention.lower() not in message.text.lower():
        await message.answer(
            f"❌ В тексте обязательно должен быть указан ваш username: {user_mention}\n"
            f"Пожалуйста, добавьте его и отправьте текст снова."
        )
        return
    
    await state.update_data(text=message.text, photos=[])
    await message.answer(
        "Хотите добавить фото к объявлению?",
        reply_markup=ask_photo_kb
    )
    await AdForm.ask_photo.set()

@dp.message_handler(lambda m: m.text == "➕ Добавить фото", state=AdForm.ask_photo)
async def add_photo_start(message: types.Message):
    await message.answer(
        f"📸 Отправьте до {MAX_PHOTOS} фото.\n"
        "После отправки всех фото нажмите «Готово».",
        reply_markup=photo_done_kb
    )
    await AdForm.photos.set()

@dp.message_handler(lambda m: m.text == "➡️ Без фото", state=AdForm.ask_photo)
async def no_photo_confirm(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await show_preview(message, data, state)

@dp.message_handler(content_types=["photo"], state=AdForm.photos)
async def process_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    
    if len(photos) >= MAX_PHOTOS:
        await message.answer(f"❌ Нельзя добавить больше {MAX_PHOTOS} фото.")
        return
    
    photos.append(message.photo[-1].file_id)
    await state.update_data(photos=photos)
    
    remaining = MAX_PHOTOS - len(photos)
    await message.answer(
        f"✅ Фото добавлено! ({len(photos)}/{MAX_PHOTOS})\n"
        f"Осталось: {remaining}\n"
        "Можете добавить ещё фото или нажать «Готово»."
    )

@dp.message_handler(lambda m: m.text == "✅ Готово", state=AdForm.photos)
async def photos_done(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await show_preview(message, data, state)

async def show_preview(message: types.Message, data: dict, state: FSMContext):
    """Показ предпросмотра объявления"""
    preview_text = f"🔍 <b>Предпросмотр объявления</b>\n\n{data['text']}"
    
    if data.get("photos"):
        preview_text += f"\n\n📸 Фото: {len(data['photos'])} шт."
    
    await message.answer(preview_text, reply_markup=confirm_kb)
    await AdForm.confirm.set()

@dp.callback_query_handler(lambda c: c.data == "cancel", state=AdForm.confirm)
async def cancel_ad(call: types.CallbackQuery, state: FSMContext):
    await state.finish()
    await call.message.edit_text("❌ Подача объявления отменена.")
    await call.message.answer("Главное меню:", reply_markup=main_kb)

@dp.callback_query_handler(lambda c: c.data == "confirm", state=AdForm.confirm)
async def confirm_ad(call: types.CallbackQuery, state: FSMContext):
    user = call.from_user
    data = await state.get_data()
    
    conn, cursor = get_cursor()
    
    # Сохраняем объявление в БД
    cursor.execute("INSERT INTO ads (user_id) VALUES (?)", (user.id,))
    ad_id = cursor.lastrowid
    
    # Обновляем время последней подачи
    current_time = int(time.time())
    cursor.execute(
        "UPDATE users SET last_ad_time = ? WHERE user_id = ?",
        (current_time, user.id)
    )
    
    conn.commit()
    conn.close()
    
    # Сохраняем данные объявления
    pending_ads[ad_id] = data
    
    await state.finish()
    
    # Отправляем модераторам
    mod_text = (
        f"📢 <b>Новое объявление №{ad_id}</b>\n\n"
        f"👤 Автор: @{user.username}\n"
        f"🆔 ID: {user.id}\n"
        f"⏱ Время подачи: {datetime.fromtimestamp(current_time).strftime('%d.%m.%Y %H:%M')}\n\n"
        f"📝 Текст:\n{data['text']}"
    )
    
    if data.get("photos"):
        mod_text += f"\n\n📸 Фото: {len(data['photos'])} шт."
    
    sent_count = 0
    for mod_id in MODERATORS:
        try:
            # Если есть фото - отправляем с фото
            if data.get("photos"):
                # Создаем медиагруппу для модератора
                media_group = []
                for i, photo_id in enumerate(data["photos"]):
                    if i == 0:
                        media_group.append(InputMediaPhoto(photo_id, caption=mod_text))
                    else:
                        media_group.append(InputMediaPhoto(photo_id))
                
                await bot.send_media_group(mod_id, media_group)
                # Отправляем клавиатуру отдельно
                await bot.send_message(mod_id, "Действия:", reply_markup=get_moderation_keyboard(ad_id))
            else:
                # Если нет фото - просто текст
                await bot.send_message(mod_id, mod_text, reply_markup=get_moderation_keyboard(ad_id))
            
            sent_count += 1
        except Exception as e:
            logging.error(f"Не удалось отправить модератору {mod_id}: {e}")
    
    # Получаем информацию об уровне для ответа пользователю
    conn, cursor = get_cursor()
    cursor.execute("SELECT referrals FROM users WHERE user_id=?", (user.id,))
    refs = cursor.fetchone()[0]
    conn.close()
    
    level_name = get_level_display(refs)
    cooldown = get_cooldown(refs)
    
    await call.message.edit_text(
        f"✅ <b>Объявление №{ad_id} отправлено на модерацию!</b>\n\n"
        f"📊 Ваш уровень: {level_name}\n"
        f"⏱ Следующая публикация будет доступна через: {format_time(cooldown)}\n"
        f"(отсчет пошел с момента подачи этого объявления)\n\n"
        f"Ожидайте проверки (обычно до 24 часов)."
    )
    await call.message.answer("Главное меню:", reply_markup=main_kb)
    
    logging.info(f"Объявление {ad_id} отправлено {sent_count} модераторам. КД для {user.id} обновлен.")

# ================= МОДЕРАЦИЯ =================

@dp.callback_query_handler(lambda c: c.data.startswith("approve:"))
async def approve_ad(call: types.CallbackQuery):
    ad_id = int(call.data.split(":")[1])
    
    if ad_id in processed_ads:
        await call.answer("❌ Это объявление уже обработано!", show_alert=True)
        return
    
    processed_ads.add(ad_id)
    
    conn, cursor = get_cursor()
    cursor.execute("SELECT user_id FROM ads WHERE id=?", (ad_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        await call.answer("❌ Объявление не найдено!", show_alert=True)
        return
    
    user_id = row[0]
    data = pending_ads.get(ad_id)
    
    if not data:
        conn.close()
        await call.answer("❌ Данные объявления утеряны!", show_alert=True)
        return
    
    # Получаем уровень пользователя
    cursor.execute("SELECT referrals FROM users WHERE user_id=?", (user_id,))
    refs = cursor.fetchone()[0]
    tag, _ = get_level(refs)
    
    # Формируем текст для публикации
    final_text = data["text"]
    if tag:
        final_text = f"{tag}\n\n{final_text}"
    
    # Добавляем текст с подпиской на канал
    final_text_with_sub = add_subscription_text(final_text)
    
    # Публикуем в канал
    try:
        if data["photos"]:
            media_group = []
            for i, photo_id in enumerate(data["photos"]):
                if i == 0:
                    media_group.append(InputMediaPhoto(photo_id, caption=final_text_with_sub))
                else:
                    media_group.append(InputMediaPhoto(photo_id))
            
            await bot.send_media_group(CHANNEL_USERNAME, media_group)
        else:
            await bot.send_message(CHANNEL_USERNAME, final_text_with_sub)
        
        # Обновляем статусы
        cursor.execute("UPDATE ads SET status='approved' WHERE id=?", (ad_id,))
        conn.commit()
        
        # Уведомляем пользователя
        await bot.send_message(
            user_id,
            f"✅ Ваше объявление №{ad_id} одобрено и опубликовано в канале!"
        )
        
        # Уведомляем ВСЕХ модераторов о результате
        for mod_id in MODERATORS:
            try:
                await bot.send_message(
                    mod_id,
                    f"📌 <b>Объявление №{ad_id} ОДОБРЕНО</b>\n"
                    f"👮 Модератор: @{call.from_user.username}"
                )
            except:
                pass
        
        await call.message.edit_reply_markup()
        await call.answer("✅ Объявление одобрено и опубликовано!")
        
    except Exception as e:
        logging.error(f"Ошибка при публикации объявления {ad_id}: {e}")
        await call.answer("❌ Ошибка при публикации!", show_alert=True)
    
    conn.close()

@dp.callback_query_handler(lambda c: c.data.startswith("reject:"))
async def reject_ad(call: types.CallbackQuery):
    ad_id = int(call.data.split(":")[1])
    
    if ad_id in processed_ads:
        await call.answer("❌ Это объявление уже обработано!", show_alert=True)
        return
    
    processed_ads.add(ad_id)
    
    conn, cursor = get_cursor()
    cursor.execute("SELECT user_id FROM ads WHERE id=?", (ad_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        await call.answer("❌ Объявление не найдено!", show_alert=True)
        return
    
    user_id = row[0]
    
    # Обновляем статус
    cursor.execute("UPDATE ads SET status='rejected' WHERE id=?", (ad_id,))
    conn.commit()
    conn.close()
    
    # Уведомляем пользователя
    await bot.send_message(
        user_id,
        f"❌ Ваше объявление №{ad_id} отклонено модератором.\n"
        f"Причина: не указано (свяжитесь с модератором для уточнения)."
    )
    
    # Уведомляем ВСЕХ модераторов о результате
    for mod_id in MODERATORS:
        try:
            await bot.send_message(
                mod_id,
                f"📌 <b>Объявление №{ad_id} ОТКЛОНЕНО</b>\n"
                f"👮 Модератор: @{call.from_user.username}"
            )
        except:
            pass
    
    await call.message.edit_reply_markup()
    await call.answer("❌ Объявление отклонено!")

# ================= РЕФЕРАЛЫ =================

@dp.message_handler(lambda m: m.text == "🎁 Рефералы")
async def show_referrals(message: types.Message):
    user_id = message.from_user.id
    
    conn, cursor = get_cursor()
    cursor.execute("SELECT referrals, last_ad_time FROM users WHERE user_id=?", (user_id,))
    result = cursor.fetchone()
    
    if not result:
        conn.close()
        await message.answer("❌ Ошибка: пользователь не найден.")
        return
    
    refs, last_ad_time = result
    
    # Получаем информацию об уровне и КД
    level_name = get_level_display(refs)
    cooldown = get_cooldown(refs)
    
    # Проверяем оставшееся время до следующей публикации
    can_post_now, remaining = can_post(user_id, refs, last_ad_time)
    
    if last_ad_time == 0:
        status = "✅ Можно подать объявление"
        remaining_text = "нет ограничений"
    elif can_post_now:
        status = "✅ Можно подать объявление"
        remaining_text = "уже можно"
    else:
        status = "⏳ КД активен"
        remaining_text = format_time(remaining)
    
    text = (
        f"👥 <b>Ваша реферальная статистика</b>\n\n"
        f"Приглашено: {refs} человек\n"
        f"Текущий уровень: {level_name}\n"
        f"КД: {format_time(cooldown)}\n"
        f"Статус: {status}\n"
        f"Осталось: {remaining_text}\n\n"
        f"🔗 <b>Ваша реферальная ссылка:</b>\n"
        f"https://t.me/{BOT_USERNAME}?start={user_id}\n\n"
        f"🏅 <b>Уровни:</b>\n"
        f"👤 Новичок (0-29) — КД {format_time(COOLDOWN_NEWBIE)}\n"
        f"🔥 Активный селлер (30-99) — КД {format_time(COOLDOWN_ACTIVE)}\n"
        f"🏆 Топ селлер (100+) — КД {format_time(COOLDOWN_TOP)}\n\n"
        f"⭐ Отметка в посте только у ТОП СЕЛЛЕРОВ\n\n"
        f"🏆 <b>Топ 10 пригласивших:</b>\n"
    )
    
    cursor.execute("SELECT user_id, referrals FROM users ORDER BY referrals DESC LIMIT 10")
    top_users = cursor.fetchall()
    conn.close()
    
    for i, (uid, ref_count) in enumerate(top_users, 1):
        try:
            user_info = await bot.get_chat(uid)
            name = f"@{user_info.username}" if user_info.username else f"ID: {uid}"
        except:
            name = f"ID: {uid}"
        
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "📌"
        text += f"{medal} {i}. {name} — {ref_count}\n"
    
    await message.answer(text)

# ================= АДМИН-КОМАНДЫ =================

@dp.message_handler(commands=["users"])
async def admin_users_count(message: types.Message):
    if message.from_user.id != OWNER_ID:
        return
    
    conn, cursor = get_cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE last_ad_time > 0")
    active_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM ads WHERE status='pending'")
    pending_ads_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM ads WHERE status='approved'")
    approved_ads = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM ads WHERE status='rejected'")
    rejected_ads = cursor.fetchone()[0]
    
    conn.close()
    
    await message.answer(
        f"📊 <b>Статистика бота</b>\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"📝 Активных (с постами): {active_users}\n"
        f"⏳ Ожидают модерации: {pending_ads_count}\n"
        f"✅ Одобрено: {approved_ads}\n"
        f"❌ Отклонено: {rejected_ads}\n"
        f"🔄 В обработке сейчас: {len(processed_ads)}"
    )

@dp.message_handler(commands=["broadcast"])
async def admin_broadcast(message: types.Message):
    if message.from_user.id != OWNER_ID:
        return
    
    text = message.get_args()
    if not text:
        await message.answer("❌ Укажите текст рассылки: /broadcast Текст")
        return
    
    conn, cursor = get_cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()
    
    sent = 0
    failed = 0
    
    status_msg = await message.answer(f"📨 Начинаю рассылку {len(users)} пользователям...")
    
    for i, (user_id,) in enumerate(users):
        try:
            await bot.send_message(user_id, f"📢 <b>Рассылка</b>\n\n{text}")
            sent += 1
        except Exception as e:
            failed += 1
        
        if i % 10 == 0:
            await status_msg.edit_text(
                f"📨 Прогресс: {i}/{len(users)}\n"
                f"✅ Отправлено: {sent}\n"
                f"❌ Ошибок: {failed}"
            )
    
    await status_msg.edit_text(
        f"✅ Рассылка завершена!\n"
        f"Отправлено: {sent}\n"
        f"Ошибок: {failed}"
    )

@dp.message_handler(commands=["clear_ads"])
async def admin_clear_ads(message: types.Message):
    """Очистка старых данных объявлений (только для админа)"""
    if message.from_user.id != OWNER_ID:
        return
    
    global pending_ads, processed_ads
    pending_ads.clear()
    processed_ads.clear()
    
    await message.answer("✅ Кэш объявлений очищен!")

@dp.message_handler(commands=["check_cooldown"])
async def check_cooldown(message: types.Message):
    """Проверка КД для пользователя (для админа)"""
    if message.from_user.id != OWNER_ID:
        return
    
    args = message.get_args()
    if not args:
        await message.answer("Укажите ID пользователя: /check_cooldown 123456789")
        return
    
    try:
        check_user_id = int(args)
    except:
        await message.answer("Некорректный ID")
        return
    
    conn, cursor = get_cursor()
    cursor.execute("SELECT referrals, last_ad_time FROM users WHERE user_id=?", (check_user_id,))
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        await message.answer(f"Пользователь {check_user_id} не найден в БД")
        return
    
    refs, last_ad_time = result
    level_name = get_level_display(refs)
    cooldown = get_cooldown(refs)
    can_post_now, remaining = can_post(check_user_id, refs, last_ad_time)
    
    last_ad_str = datetime.fromtimestamp(last_ad_time).strftime('%d.%m.%Y %H:%M:%S') if last_ad_time > 0 else "никогда"
    
    await message.answer(
        f"📊 <b>Информация о пользователе {check_user_id}</b>\n\n"
        f"Рефералов: {refs}\n"
        f"Уровень: {level_name}\n"
        f"КД: {format_time(cooldown)}\n"
        f"Последняя подача: {last_ad_str}\n"
        f"Может подать сейчас: {'✅' if can_post_now else '❌'}\n"
        f"Осталось: {format_time(remaining) if not can_post_now else '0'}"
    )

@dp.message_handler(commands=["db_path"])
async def show_db_path(message: types.Message):
    """Показать путь к базе данных (для отладки)"""
    if message.from_user.id != OWNER_ID:
        return
    
    await message.answer(
        f"📂 <b>Информация о БД</b>\n\n"
        f"Путь: {DB_PATH}\n"
        f"Папка существует: {'✅' if os.path.exists(DATA_DIR) else '❌'}\n"
        f"Файл БД существует: {'✅' if os.path.exists(DB_PATH) else '❌'}\n"
        f"Размер файла: {os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0} байт"
    )

# ================= ОБРАБОТЧИКИ ОШИБОК =================

@dp.errors_handler()
async def errors_handler(update, exception):
    """Глобальный обработчик ошибок"""
    logging.error(f"Ошибка: {exception} | Update: {update}")
    return True

# ================= ЗАПУСК =================

if __name__ == "__main__":
    logging.info("Бот запущен...")
    executor.start_polling(dp, skip_updates=True)
