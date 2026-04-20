import asyncio
import logging
from datetime import datetime, timedelta
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramForbiddenError
from motor.motor_asyncio import AsyncIOMotorClient

# --- КОНФИГУРАЦИЯ ---
API_TOKEN = '8708528114:AAE2o48onjYjZGrEGJXwPwZC3yYAVSwqI6k'
ADMIN_ID = 1470008106
MONGO_URL = "mongodb+srv://verholancevg_db_user:nSKwzPzbPHa4Haui@cluster0.59qdy3c.mongodb.net/?appName=Cluster0"

# Прямые ссылки на иконки (максимально стабильные)
FIRE_ICON = "https://githubusercontent.com"
STATS_ICON = "https://githubusercontent.com"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

cluster = AsyncIOMotorClient(MONGO_URL)
db = cluster.streak_db
series_col = db.series
users_col = db.users

# --- ФУНКЦИИ ВРЕМЕНИ (МСК) ---

def get_msk_now():
    return datetime.utcnow() + timedelta(hours=3)

# --- ЛОГИКА ОПОВЕЩЕНИЙ ---

async def send_safe_msg(user_id, text, kb=None):
    try:
        await bot.send_message(int(user_id), text, reply_markup=kb)
    except TelegramForbiddenError:
        pass

async def check_alerts_loop():
    while True:
        now_msk = get_msk_now()
        today_str = now_msk.strftime('%Y-%m-%d')
        
        # 1. ОПОВЕЩЕНИЕ ЗА 1 ЧАС (в 23:00 по МСК)
        if now_msk.hour == 23:
            async for streak in series_col.find({"last_date": {"$ne": today_str}, "warned_today": {"$ne": today_str}}):
                user_ids = streak['key'].split("_")
                for uid in user_ids:
                    await send_safe_msg(uid, 
                        f"⚡ Огонёк почти погас!\n────────────────────\n"
                        f"У вас остался всего 1 час, чтобы продлить серию в {streak['streak']} дн.\n"
                        f"Скорее используй @streakttbot 🔥"
                    )
                await series_col.update_one({"key": streak['key']}, {"$set": {"warned_today": today_str}})

        # 2. ПРОВЕРКА СГОРЕВШИХ (раз в час)
        async for streak in series_col.find({"notified": 0}):
            last_date = datetime.strptime(streak['last_date'], '%Y-%m-%d').date()
            if now_msk.date() > last_date + timedelta(days=1):
                user_ids = streak['key'].split("_")
                kb = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="💎 Восстановить серию", callback_data=f"res_{streak['key']}")
                ]])
                for uid in user_ids:
                    await send_safe_msg(uid, 
                        f"🕯 Огонёк серии потух!\n────────────────────\n"
                        f"Ваша связь длиной в {streak['streak']} дн. оборвалась.\n"
                        f"Используй восстановление, если остались попытки ✨",
                        kb=kb if streak.get('saves', 3) > 0 else None
                    )
                await series_col.update_one({"key": streak['key']}, {"$set": {"notified": 1}})

        await asyncio.sleep(600)

# --- ВЕБ-СЕРВЕР И ОБРАБОТЧИКИ ---

async def handle(request): return web.Response(text="Alive")
async def start_webserver():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', 10000).start()

async def track_user(user: types.User):
    username = f"@{user.username}" if user.username else "нет имени"
    await users_col.update_one({"id": user.id}, {"$set": {"username": username, "first_name": user.first_name}}, upsert=True)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await track_user(message.from_user)
    await message.answer("✨ Бот активен! Используй @streakttbot в чатах.\n────────────────────\n▫️ /stats — твои успехи\n▫️ /users — участники")

@dp.message(Command("users"))
async def cmd_users(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    users = await users_col.find().to_list(length=100)
    user_list = "\n".join([f"▫️ {u['first_name']} — {u['username']}" for u in users])
    await message.answer(f"👥 Участники бота:\n────────────────────\n{user_list if user_list else 'Пусто'}")

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    uid = str(message.from_user.id)
    user_series = await series_col.find({"key": {"$regex": uid}}).to_list(length=100)
    total = sum(s['streak'] for s in user_series)
    await message.answer(f"📊 Твоя статистика:\n────────────────────\n🔥 Всего дней: {total}\n👥 Активных связей: {len(user_series)}")

@dp.inline_query()
async def inline_handler(query: InlineQuery):
    await track_user(query.from_user)
    uid = query.from_user.id
    results = [
        InlineQueryResultArticle(
            id="fire", 
            title="⚡ Продлить огонёк", 
            description="Поддержать ежедневную связь",
            thumbnail_url=FIRE_ICON,
            thumbnail_width=96,
            thumbnail_height=96,
            input_message_content=InputTextMessageContent(message_text="✨ Нажми кнопку ниже, чтобы продлить серию 🔥"),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Продлить", callback_data=f"acc_{uid}")]])
        ),
        InlineQueryResultArticle(
            id="check", 
            title="🏆 Сколько дней?", 
            description="Узнать ваш общий рекорд",
            thumbnail_url=STATS_ICON,
            thumbnail_width=96,
            thumbnail_height=96,
            input_message_content=InputTextMessageContent(message_text="📊 Нажми кнопку, чтобы проверить огонёк"),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📊 Показать дни", callback_data=f"show_{uid}")]])
        )
    ]
    await query.answer(results, cache_time=1, is_personal=True)

@dp.callback_query(F.data.startswith("acc_"))
async def process_acc(callback: types.CallbackQuery):
    sender_id = int(callback.data.split("_")[1])
    receiver_id = callback.from_user.id
    if sender_id == receiver_id:
        await callback.answer("❌ Это твой вызов!", show_alert=True); return
    
    key = f"{min(sender_id, receiver_id)}_{max(sender_id, receiver_id)}"
    now_msk = get_msk_now()
    today_str = now_msk.strftime('%Y-%m-%d')
    yesterday_str = (now_msk - timedelta(days=1)).strftime('%Y-%m-%d')
    
    streak_doc = await series_col.find_one({"key": key})
    if streak_doc:
        if streak_doc['last_date'] == today_str:
            await callback.answer()
            await bot.edit_message_text(text="✨ Огонёк на сегодня уже зажжён", inline_message_id=callback.inline_message_id)
            return
        new_streak = streak_doc['streak'] + 1 if streak_doc['last_date'] == yesterday_str else 1
        saves = streak_doc.get('saves', 3)
    else: new_streak, saves = 1, 3
    
    await series_col.update_one({"key": key}, {"$set": {"streak": new_streak, "last_date": today_str, "notified": 0, "saves": saves, "warned_today": ""}}, upsert=True)
    await callback.answer()
    await bot.edit_message_text(text=f"🔥 Огонёк продлён!\n────────────────────\n📈 Текущая серия: {new_streak} дн.", inline_message_id=callback.inline_message_id)

@dp.callback_query(F.data.startswith("res_"))
async def process_restore(callback: types.CallbackQuery):
    key = callback.data.replace("res_", "")
    today_str = get_msk_now().strftime('%Y-%m-%d')
    streak_doc = await series_col.find_one({"key": key})
    if streak_doc and streak_doc.get('saves', 0) > 0:
        await series_col.update_one({"key": key}, {"$set": {"last_date": today_str, "saves": streak_doc['saves'] - 1, "notified": 0, "warned_today": ""}})
        await callback.message.edit_text(f"💎 Серия восстановлена!\n────────────────────\n🔥 Сохранен прогресс: {streak_doc['streak']} дн.")
    else: await callback.answer("❌ Попытки закончились", show_alert=True)

@dp.callback_query(F.data.startswith("show_"))
async def process_show(callback: types.CallbackQuery):
    sender_id = int(callback.data.split("_")[1])
    key = f"{min(sender_id, callback.from_user.id)}_{max(sender_id, callback.from_user.id)}"
    streak_doc = await series_col.find_one({"key": key})
    await callback.answer()
    await bot.edit_message_text(f"🔥 Ваша совместная серия: {streak_doc['streak'] if streak_doc else 0} дн.", inline_message_id=callback.inline_message_id)

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(check_alerts_loop())
    await asyncio.gather(start_webserver(), dp.start_polling(bot))

if __name__ == '__main__':
    asyncio.run(main())
