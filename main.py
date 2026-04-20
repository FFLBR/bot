import asyncio
import logging
import random
from datetime import datetime, timedelta
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from motor.motor_asyncio import AsyncIOMotorClient

# --- КОНФИГУРАЦИЯ ---
API_TOKEN = '8708528114:AAE2o48onjYjZGrEGJXwPwZC3yYAVSwqI6k'
ADMIN_ID = 1470008106
MONGO_URL = "mongodb+srv://verholancevg_db_user:nSKwzPzbPHa4Haui@cluster0.59qdy3c.mongodb.net/?appName=Cluster0"

# Иконки (GitHub — самое надежное хранилище для Telegram)
FIRE_ICON = "https://githubusercontent.com"
STATS_ICON = "https://githubusercontent.com"
GEAR_ICON = "https://githubusercontent.com"
LOCK_ICON = "https://githubusercontent.com"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

cluster = AsyncIOMotorClient(MONGO_URL)
db = cluster.streak_db
series_col = db.series
users_col = db.users

EMOJI_LIST = [
    {"emoji": "⚡", "name": "Молния", "days": 0},
    {"emoji": "🔥", "name": "Огонь", "days": 0},
    {"emoji": "⭐", "name": "Звезда", "days": 2},
    {"emoji": "❤️", "name": "Сердце", "days": 4},
    {"emoji": "❤️‍🔥", "name": "Жар", "days": 7},
    {"emoji": "🍌", "name": "Банан", "days": 10},
    {"emoji": "🍆", "name": "Баклажан", "days": 15},
    {"emoji": "🐋", "name": "Кит", "days": 30},
    {"emoji": "💎", "name": "Алмаз", "days": 30},
]

# --- СИСТЕМНЫЕ ФУНКЦИИ ---

def get_msk_now():
    """Текущее время по Москве"""
    return datetime.utcnow() + timedelta(hours=3)

async def track_user(user: types.User):
    """Регистрация пользователя в базе"""
    await users_col.update_one(
        {"id": user.id},
        {"$set": {"username": f"@{user.username}" if user.username else "нет", "first_name": user.first_name}},
        upsert=True
    )

async def is_registered(user_id: int):
    """Проверка, запускал ли юзер бота"""
    user = await users_col.find_one({"id": user_id})
    return user is not None

async def send_safe_msg(user_id, text, kb=None):
    """Отправка сообщения с защитой от ошибок"""
    try:
        await bot.send_message(int(user_id), text, reply_markup=kb)
        return True
    except:
        return False

# --- ФОНОВАЯ ЛОГИКА ---

async def check_alerts_loop():
    while True:
        now = get_msk_now()
        today_s = now.strftime('%Y-%m-%d')
        
        # 1. Напоминание в 23:00 МСК
        if now.hour == 23:
            async for s in series_col.find({"last_date": {"$ne": today_s}, "warned": {"$ne": today_s}}):
                for uid in s['key'].split("_"):
                    await send_safe_msg(uid, "⚡ Огонёк почти погас!\nОстался всего 1 час до сброса вашей серии. 🔥")
                await series_col.update_one({"key": s['key']}, {"$set": {"warned": today_s}})

        # 2. Уведомление о сгорании
        async for s in series_col.find({"notified": 0}):
            ld = datetime.strptime(s['last_date'], '%Y-%m-%d').date()
            if now.date() > ld + timedelta(days=1):
                kb = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="💎 Восстановить серию", callback_data=f"res_{s['key']}")
                ]])
                for uid in s['key'].split("_"):
                    await send_safe_msg(uid, f"🕯 Огонёк серии потух!\nСвязь в {s['streak']} дн. оборвалась.", 
                                        kb=kb if s.get('saves', 3) > 0 else None)
                await series_col.update_one({"key": s['key']}, {"$set": {"notified": 1}})
        
        await asyncio.sleep(600)

# --- ИНЛАЙН РЕЖИМ (@) ---

@dp.inline_query()
async def inline_handler(query: InlineQuery):
    uid = query.from_user.id
    await track_user(query.from_user)
    cb = random.randint(1, 999) # Для обновления картинок

    if not await is_registered(uid):
        results = [InlineQueryResultArticle(
            id="auth", title="🔒 Активируй серийчик", thumbnail_url=f"{LOCK_ICON}?v={cb}",
            description="Нажми, чтобы начать пользоваться ботом",
            input_message_content=InputTextMessageContent(message_text="👋 Чтобы копить огоньки, сначала запусти меня в личке! ✨"),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🚀 Запустить", url=f"https://t.me{(await bot.get_me()).username}?start=1")
            ]]))
        ]
        await query.answer(results, cache_time=1, is_personal=True)
        return

    results = [
        InlineQueryResultArticle(id="acc", title="⚡ Продлить огонёк", thumbnail_url=f"{FIRE_ICON}?v={cb}",
            description="Поддержать ежедневную связь",
            input_message_content=InputTextMessageContent(message_text="✨ Нажми кнопку ниже, чтобы продлить серию 🔥"),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Продлить", callback_data=f"acc_{uid}")]] ) ),
        
        InlineQueryResultArticle(id="shw", title="🏆 Сколько дней?", thumbnail_url=f"{STATS_ICON}?v={cb}",
            description="Узнать рекорд в этом чате",
            input_message_content=InputTextMessageContent(message_text="📊 Нажми кнопку, чтобы проверить огонёк"),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📊 Показать дни", callback_data=f"shw_{uid}")]] ) ),
        
        InlineQueryResultArticle(id="pk", title="🎨 Сменить символ", thumbnail_url=f"{GEAR_ICON}?v={cb}",
            description="Выбрать новый эмодзи для серии",
            input_message_content=InputTextMessageContent(message_text="🎨 Настройка символа серии..."),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚙️ Настройки", callback_data=f"pk_{uid}")]] ) )
    ]
    await query.answer(results, cache_time=1, is_personal=True)

# --- ЛОГИКА КНОПОК ---

@dp.callback_query(F.data.startswith("acc_"))
async def process_acc(callback: types.CallbackQuery):
    if not await is_registered(callback.from_user.id):
        await callback.answer("❌ Сначала нажми /start в личке бота!", show_alert=True); return

    sid = int(callback.data.split("_")[1])
    rid = callback.from_user.id
    if sid == rid:
        await callback.answer("❌ Нужно, чтобы огонёк принял другой человек!", show_alert=True); return
    
    key = f"{min(sid, rid)}_{max(sid, rid)}"
    now = get_msk_now()
    today, yest = now.strftime('%Y-%m-%d'), (now - timedelta(days=1)).strftime('%Y-%m-%d')
    
    s = await series_col.find_one({"key": key})
    emoji = s.get('emoji', "🔥") if s else "🔥"
    
    if s:
        if s['last_date'] == today:
            await callback.answer()
            await bot.edit_message_text(f"{emoji} Огонёк в этом чате уже зажжён", inline_message_id=callback.inline_message_id)
            return
        new_streak = s['streak'] + 1 if s['last_date'] == yest else 1
        saves = s.get('saves', 3)
    else: new_streak, saves = 1, 3
    
    await series_col.update_one({"key": key}, {"$set": {"streak": new_streak, "last_date": today, "notified": 0, "saves": saves, "warned": ""}}, upsert=True)
    await callback.answer()
    await bot.edit_message_text(f"{emoji} Огонёк продлён!\n────────────────────\n📈 Текущая серия: {new_streak} дн.", inline_message_id=callback.inline_message_id)

@dp.callback_query(F.data.startswith("shw_"))
async def process_shw(callback: types.CallbackQuery):
    if not await is_registered(callback.from_user.id):
        await callback.answer("❌ Сначала нажми /start в личке бота!", show_alert=True); return
    sid = int(callback.data.split("_")[1])
    key = f"{min(sid, callback.from_user.id)}_{max(sid, callback.from_user.id)}"
    s = await series_col.find_one({"key": key})
    await callback.answer()
    await bot.edit_message_text(f"🔥 Ваша серия в этом чате: {s['streak'] if s else 0} дн.", inline_message_id=callback.inline_message_id)

@dp.callback_query(F.data.startswith("pk_"))
async def process_pk(callback: types.CallbackQuery):
    if not await is_registered(callback.from_user.id):
        await callback.answer("❌ Сначала нажми /start в личке бота!", show_alert=True); return
    sid = int(callback.data.split("_")[1])
    key = f"{min(sid, callback.from_user.id)}_{max(sid, callback.from_user.id)}"
    s = await series_col.find_one({"key": key})
    days = s['streak'] if s else 0
    kb, row = [], []
    for i in EMOJI_LIST:
        if days >= i['days']:
            row.append(InlineKeyboardButton(text=f"{i['emoji']} {i['name']}", callback_data=f"set_{i['emoji']}_{key}"))
        else:
            row.append(InlineKeyboardButton(text=f"🔒 {i['days']} дн.", callback_data="lck"))
        if len(row) == 2: kb.append(row); row = []
    if row: kb.append(row)
    await bot.edit_message_text(f"🎨 Выбор символа\nСерия: {days} дн.\n────────────────────", inline_message_id=callback.inline_message_id, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("set_"))
async def process_set(callback: types.CallbackQuery):
    p = callback.data.split("_")
    emoji, key = p[1], "_".join(p[2:])
    await series_col.update_one({"key": key}, {"$set": {"emoji": emoji}})
    await callback.answer(f"Символ {emoji} установлен!", show_alert=True)
    await bot.edit_message_text(f"✨ Новый символ серии: {emoji}\nОн появится при следующем продлении!", inline_message_id=callback.inline_message_id)

@dp.callback_query(F.data == "lck")
async def process_lck(callback: types.CallbackQuery):
    await callback.answer("Этот символ еще закрыт! Нужно больше дней. 🔒", show_alert=True)

# --- ЛИЧКА БОТА ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await track_user(message.from_user)
    await message.answer("✨ Бот активен! Теперь используй @streakttbot в чатах.\n────────────────────\n▫️ /stats — твои успехи\n▫️ /users — участники")

@dp.message(Command("users"))
async def cmd_users(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    users = await users_col.find().to_list(length=100)
    user_list = "\n".join([f"▫️ {u['first_name']} — {u['username']}" for u in users])
    await message.answer(f"👥 Участники:\n────────────────────\n{user_list if user_list else 'Пусто'}")

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    uid = str(message.from_user.id)
    # Поиск по точному ID в ключе пары
    user_series = await series_col.find({"$or": [{"key": {"$regex": f"^{uid}_"}}, {"key": {"$regex": f"_{uid}$"}}]}).to_list(length=100)
    total = sum(s['streak'] for s in user_series)
    await message.answer(f"📊 Твоя статистика:\n────────────────────\n🔥 Всего дней: {total}\n👥 Активных серий: {len(user_series)}")

@dp.message(Command("broadcast"))
async def cmd_brd(message: types.Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID or not command.args: return
    users = await users_col.find().to_list(length=1000)
    for u in users: await send_safe_msg(u['id'], f"📣 Сообщение:\n────────────────────\n{command.args}")
    await message.answer("✅ Отправлено.")

@dp.callback_query(F.data.startswith("res_"))
async def process_res(callback: types.CallbackQuery):
    key = callback.data.replace("res_", "")
    s = await series_col.find_one({"key": key})
    if s and s.get('saves', 0) > 0:
        await series_col.update_one({"key": key}, {"$set": {"last_date": get_msk_now().strftime('%Y-%m-%d'), "saves": s['saves']-1, "notified": 0, "warned": ""}})
        await callback.message.edit_text(f"💎 Серия восстановлена! Прогресс: {s['streak']} дн.")
    else: await callback.answer("❌ Попытки закончились", show_alert=True)

# --- СЕРВЕР ---
async def handle(request): return web.Response(text="Alive")
async def start_webserver():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', 10000).start()

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(check_alerts_loop())
    await asyncio.gather(start_webserver(), dp.start_polling(bot))

if __name__ == '__main__':
    asyncio.run(main())
