import asyncio
import sqlite3
import logging
import hashlib
import random
from datetime import datetime, timedelta
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent, InlineKeyboardMarkup, InlineKeyboardButton

# --- ТВОИ ДАННЫЕ (УЖЕ ВСТАВЛЕНЫ) ---
API_TOKEN = '8708528114:AAE2o48onjYjZGrEGJXwPwZC3yYAVSwqI6k'
ADMIN_ID = 1470008106 

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect('ultimate_series.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pair_series (
            pair_key TEXT PRIMARY KEY,
            streak_count INTEGER DEFAULT 0,
            last_date TEXT,
            last_user_id INTEGER
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            username TEXT
        )
    ''')
    conn.commit()
    conn.close()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def get_heart_rank(days):
    if days < 5: return "🤍 (Новички)"
    if days < 15: return "💛 (Друзья)"
    if days < 30: return "🧡 (Близкие)"
    if days < 50: return "❤️ (Лучшие)"
    return "💖 (Легенды)"

async def track_user(user: types.User):
    conn = sqlite3.connect('ultimate_series.db')
    cursor = conn.cursor()
    username = f"@{user.username}" if user.username else "нет юзернейма"
    cursor.execute('INSERT OR REPLACE INTO users VALUES (?, ?, ?)', (user.id, user.first_name, username))
    conn.commit()
    conn.close()

# --- МИНИ ВЕБ-СЕРВЕР ДЛЯ RENDER (ЧТОБЫ НЕ ПАДАЛ ПО ПОРТУ) ---
async def handle(request):
    return web.Response(text="Bot is alive!")

async def start_webserver():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 10000)
    await site.start()

# --- ОБРАБОТЧИКИ В ЛИЧКЕ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await track_user(message.from_user)
    await message.answer(
        "✨ **Добро пожаловать в Личный Кабинет!** ✨\n\n"
        "Чтобы зажечь огонёк с другом, начни писать `@твой_бот` в любом чате!\n\n"
        "📊 **Команды:**\n"
        "/my_series — Твои активные огоньки\n"
        "/users — Все пользователи (только админу)\n"
        "/help — Инструкция",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Попробовать инлайн", switch_inline_query_current_chat="")]
        ])
    )

@dp.message(Command("users"))
async def cmd_users(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("🤫 Только админ видит этот список!")
        return
    conn = sqlite3.connect('ultimate_series.db')
    cursor = conn.cursor()
    cursor.execute('SELECT first_name, username FROM users')
    rows = cursor.fetchall()
    conn.close()
    text = "👥 **Активировали бота:**\n\n" + "\n".join([f"{i+1}. {r[0]} ({r[1]})" for i, r in enumerate(rows)])
    await message.answer(text)

@dp.message(Command("my_series"))
async def cmd_my_series(message: types.Message):
    my_id = message.from_user.id
    conn = sqlite3.connect('ultimate_series.db')
    cursor = conn.cursor()
    cursor.execute('SELECT streak_count, last_date FROM pair_series WHERE pair_key LIKE ?', (f"%{my_id}%",))
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        await message.answer("🥺 Пока нет активных серий.")
        return
    text = "📋 **Твои активные серии:**\n\n"
    for count, date in rows:
        text += f"✨ Серия: `{count}` дн. {get_heart_rank(count)}\n🗓 Последний раз: {date}\n\n"
    await message.answer(text, parse_mode="Markdown")

# --- ИНЛАЙН РЕЖИМ ---
@dp.inline_query()
async def inline_handler(query: InlineQuery):
    await track_user(query.from_user)
    results = [
        InlineQueryResultArticle(
            id="fire_send",
            title="🔥 Продлить огонёк серии",
            description="Отправить вызов другу",
            input_message_content=InputTextMessageContent(
                message_text=f"✨ **{query.from_user.first_name}** хочет продлить серию с тобой! 🔥"
            ),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Принять огонёк", callback_data=f"accept_{query.from_user.id}")]
            ])
        )
    ]
    await query.answer(results, cache_time=1)

@dp.callback_query(F.data.startswith("accept_"))
async def process_accept(callback: types.CallbackQuery):
    sender_id = int(callback.data.split("_")[1])
    receiver_id = callback.from_user.id
    if sender_id == receiver_id:
        await callback.answer("❌ Нельзя принять свой огонёк!", show_alert=True)
        return
    pair_key = f"{min(sender_id, receiver_id)}_{max(sender_id, receiver_id)}"
    today = datetime.now().date()
    conn = sqlite3.connect('ultimate_series.db')
    cursor = conn.cursor()
    cursor.execute('SELECT streak_count, last_date FROM pair_series WHERE pair_key = ?', (pair_key,))
    row = cursor.fetchone()
    if row:
        streak, last_date_str = row
        last_date = datetime.strptime(last_date_str, '%Y-%m-%d').date()
        if last_date == today:
            await callback.answer("🎀 Уже зажжено на сегодня!", show_alert=True)
            conn.close()
            return
        streak = streak + 1 if last_date == today - timedelta(days=1) else 1
    else:
        streak = 1
    cursor.execute('INSERT OR REPLACE INTO pair_series VALUES (?, ?, ?, ?)', (pair_key, streak, today.strftime('%Y-%m-%d'), receiver_id))
    conn.commit()
    conn.close()
    await callback.message.edit_text(
        f"🔥 **Серия продлена!**\n📊 Дней подряд: `{streak}`\n❤️ Статус: {get_heart_rank(streak)}\n👤 Принял: {callback.from_user.first_name}"
    )

# --- ЗАПУСК ---
async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await asyncio.gather(
        start_webserver(),
        dp.start_polling(bot)
    )

if __name__ == '__main__':
    asyncio.run(main())
