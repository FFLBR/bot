import asyncio
import logging
import random
from datetime import datetime, timedelta
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent, InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient

# --- КОНФИГУРАЦИЯ ---
API_TOKEN = '8708528114:AAHWYLLOuclOlcKOo9GhLPjQkZaJmzNBMKA'
ADMIN_ID = 1470008106
MONGO_URL = "mongodb+srv://verholancevg_db_user:nSKwzPzbPHa4Haui@cluster0.59qdy3c.mongodb.net/?appName=Cluster0"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Подключение к MongoDB
cluster = AsyncIOMotorClient(MONGO_URL)
db = cluster.streak_db
series_col = db.series
users_col = db.users

# Иконки
FIRE_ICON = "https://icons8.com"
STATS_ICON = "https://icons8.com"

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def get_celebration(days):
    if days == 7: return "\n🎊 Неделя пролетела незаметно!"
    if days == 20: return "\n🎈 20 дней — это уже серьезно!"
    if days == 50: return "\n💎 Половина сотни! Вы легенды!"
    if days == 100: return "\n👑 100 ДНЕЙ! Абсолютный рекорд! 🏆"
    return ""

async def track_user(user: types.User):
    username = f"@{user.username}" if user.username else "нет имени"
    await users_col.update_one(
        {"id": user.id},
        {"$set": {"username": username, "first_name": user.first_name}},
        upsert=True
    )

# --- ФОНОВАЯ ПРОВЕРКА СГОРЕВШИХ СЕРИЙ ---
async def check_dead_streaks():
    while True:
        await asyncio.sleep(3600) # Проверка раз в час
        today = datetime.now().date()
        async for streak_doc in series_col.find({"notified": 0}):
            last_date = datetime.strptime(streak_doc['last_date'], '%Y-%m-%d').date()
            if today > last_date + timedelta(days=1):
                user_ids = streak_doc['key'].split("_")
                kb = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="💎 Восстановить серию", callback_data=f"res_{streak_doc['key']}")
                ]])
                for uid in user_ids:
                    try:
                        await bot.send_message(
                            int(uid),
                            f"🕯 Огонёк серии потух!\n────────────────────\n"
                            f"Ваша связь в {streak_doc['streak']} дн. оборвалась.\n"
                            f"Осталось попыток восстановления: {streak_doc.get('saves', 3)}",
                            reply_markup=kb if streak_doc.get('saves', 3) > 0 else None
                        )
                    except: pass
                await series_col.update_one({"key": streak_doc['key']}, {"$set": {"notified": 1}})

# --- ВЕБ-СЕРВЕР ДЛЯ RENDER ---
async def handle(request): return web.Response(text="Alive")
async def start_webserver():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', 10000).start()

# --- ОБРАБОТЧИКИ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await track_user(message.from_user)
    await message.answer("✨ Бот активен! Используй @streakttbot в чатах.\n────────────────────\n▫️ /stats — твои успехи\n▫️ /users — все участники")

@dp.message(Command("users"))
async def cmd_users(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    users = await users_col.find().to_list(length=100)
    if not users:
        await message.answer("💬 Список пуст."); return
    user_list = "\n".join([f"▫️ {u['first_name']} — {u['username']}" for u in users])
    await message.answer(f"👥 Участники бота:\n────────────────────\n{user_list}")

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    uid = str(message.from_user.id)
    # Ищем серии, где ID пользователя есть в ключе (например "123_456")
    user_series = await series_col.find({"key": {"$regex": uid}}).to_list(length=100)
    total = sum(s['streak'] for s in user_series)
    await message.answer(f"📊 Твоя статистика:\n────────────────────\n🔥 Всего дней в сериях: {total}\n👥 Активных связей: {len(user_series)}")

@dp.inline_query()
async def inline_handler(query: InlineQuery):
    await track_user(query.from_user)
    uid = query.from_user.id
    results = [
        InlineQueryResultArticle(
            id="fire", title="⚡ Продлить огонёк", thumbnail_url=FIRE_ICON,
            input_message_content=InputTextMessageContent(message_text="✨ Нажми кнопку ниже, чтобы продлить серию 🔥"),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Продлить", callback_data=f"acc_{uid}")]])
        ),
        InlineQueryResultArticle(
            id="check", title="🏆 Сколько дней?", thumbnail_url=STATS_ICON,
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
    today = datetime.now().date()
    streak_doc = await series_col.find_one({"key": key})

    if streak_doc:
        last_date = datetime.strptime(streak_doc['last_date'], '%Y-%m-%d').date()
        if last_date == today:
            await callback.answer()
            await bot.edit_message_text(text="✨ Огонёк на сегодня уже зажжён", inline_message_id=callback.inline_message_id)
            await asyncio.sleep(3)
            await bot.edit_message_text(text="✨ Нажми кнопку ниже, чтобы продлить серию 🔥", 
                                        inline_message_id=callback.inline_message_id,
                                        reply_markup=callback.message.reply_markup if callback.message else None)
            return
        new_streak = streak_doc['streak'] + 1 if last_date == today - timedelta(days=1) else 1
        saves = streak_doc.get('saves', 3)
    else:
        new_streak, saves = 1, 3

    await series_col.update_one(
        {"key": key},
        {"$set": {"streak": new_streak, "last_date": today.strftime('%Y-%m-%d'), "notified": 0, "saves": saves}},
        upsert=True
    )
    await callback.answer()
    await bot.edit_message_text(
        text=f"🔥 Огонёк в этом чате продлён!\n────────────────────\n📈 Текущая серия: {new_streak} дн. {get_celebration(new_streak)}",
        inline_message_id=callback.inline_message_id
    )

@dp.callback_query(F.data.startswith("res_"))
async def process_restore(callback: types.CallbackQuery):
    key = callback.data.replace("res_", "")
    today = datetime.now().date()
    streak_doc = await series_col.find_one({"key": key})

    if streak_doc and streak_doc.get('saves', 0) > 0:
        new_saves = streak_doc['saves'] - 1
        await series_col.update_one(
            {"key": key},
            {"$set": {"last_date": today.strftime('%Y-%m-%d'), "saves": new_saves, "notified": 0}}
        )
        await callback.message.edit_text(f"💎 Серия восстановлена!\n────────────────────\n🔥 Прогресс: {streak_doc['streak']} дн.\n✨ Осталось попыток: {new_saves}")
    else:
        await callback.answer("❌ Попытки закончились", show_alert=True)

@dp.callback_query(F.data.startswith("show_"))
async def process_show(callback: types.CallbackQuery):
    sender_id = int(callback.data.split("_")[1])
    key = f"{min(sender_id, callback.from_user.id)}_{max(sender_id, callback.from_user.id)}"
    streak_doc = await series_col.find_one({"key": key})
    await callback.answer()
    await bot.edit_message_text(f"🔥 Ваша совместная серия: {streak_doc['streak'] if streak_doc else 0} дн.", inline_message_id=callback.inline_message_id)

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(check_dead_streaks())
    await asyncio.gather(start_webserver(), dp.start_polling(bot))

if __name__ == '__main__':
    asyncio.run(main())
