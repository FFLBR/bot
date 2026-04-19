import asyncio
import sqlite3
import logging
from datetime import datetime, timedelta
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent, InlineKeyboardMarkup, \
    InlineKeyboardButton
from aiogram.exceptions import TelegramForbiddenError

# --- КОНФИГУРАЦИЯ ---
API_TOKEN = '8708528114:AAE2o48onjYjZGrEGJXwPwZC3yYAVSwqI6k'
ADMIN_ID = 1470008106

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

FIRE_ICON = "https://icons8.com"
STATS_ICON = "https://icons8.com"


# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect('series_final.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS series
                      (
                          key
                          TEXT
                          PRIMARY
                          KEY,
                          streak
                          INTEGER,
                          last_date
                          TEXT,
                          saves
                          INTEGER
                          DEFAULT
                          3,
                          notified
                          INTEGER
                          DEFAULT
                          0
                      )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS users
                      (
                          id
                          INTEGER
                          PRIMARY
                          KEY,
                          username
                          TEXT,
                          first_name
                          TEXT
                      )''')
    conn.commit()
    conn.close()


def track_user(user: types.User):
    conn = sqlite3.connect('series_final.db')
    cursor = conn.cursor()
    username = f"@{user.username}" if user.username else "нет юзернейма"
    cursor.execute('INSERT OR REPLACE INTO users VALUES (?, ?, ?)', (user.id, username, user.first_name))
    conn.commit()
    conn.close()


# --- ФОНОВАЯ ПРОВЕРКА СГОРЕВШИХ СЕРИЙ ---
async def check_dead_streaks():
    while True:
        await asyncio.sleep(3600)
        today = datetime.now().date()
        conn = sqlite3.connect('series_final.db')
        cursor = conn.cursor()
        cursor.execute('SELECT key, streak, last_date, saves FROM series WHERE notified = 0')
        rows = cursor.fetchall()

        for key, streak, last_date_str, saves in rows:
            last_date = datetime.strptime(last_date_str, '%Y-%m-%d').date()
            if today > last_date + timedelta(days=1):
                user_ids = key.split("_")
                kb = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="💎 Восстановить серию", callback_data=f"res_{key}")
                ]])
                for uid in user_ids:
                    try:
                        await bot.send_message(
                            int(uid),
                            f"🕯 Огонёк серии потух!\n────────────────────\n"
                            f"Ваша связь в {streak} дн. оборвалась.\n"
                            f"Осталось попыток восстановления: {saves}",
                            reply_markup=kb if saves > 0 else None
                        )
                    except:
                        pass
                cursor.execute('UPDATE series SET notified = 1 WHERE key = ?', (key,))
        conn.commit()
        conn.close()


# --- ВЕБ-СЕРВЕР ДЛЯ RENDER ---
async def handle(request): return web.Response(text="Alive")


async def start_webserver():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()  # <--- ИСПРАВЛЕНО (строчка, из-за которой была ошибка)
    site = web.TCPSite(runner, '0.0.0.0', 10000)
    await site.start()


# --- ОБЫЧНЫЕ КОМАНДЫ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    track_user(message.from_user)
    await message.answer(
        "✨ Бот активен! Используй @streakttbot в чатах.\n────────────────────\n▫️ /stats — твои успехи\n▫️ /users — все участники")


@dp.message(Command("users"))
async def cmd_users(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("🔒 Доступ только для владельца");
        return

    conn = sqlite3.connect('series_final.db')
    cursor = conn.cursor()
    cursor.execute('SELECT first_name, username FROM users')
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await message.answer("💬 База пользователей пуста.");
        return

    user_list = "\n".join([f"▫️ {name} — {uname}" for name, uname in rows])
    await message.answer(f"👥 Участники бота:\n────────────────────\n{user_list}")


@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    track_user(message.from_user)
    uid = message.from_user.id
    conn = sqlite3.connect('series_final.db')
    cursor = conn.cursor()
    cursor.execute('SELECT streak FROM series WHERE key LIKE ?', (f"%{uid}%",))
    rows = [r[0] for r in cursor.fetchall()]
    conn.close()

    total = sum(rows)
    await message.answer(
        f"📊 Твоя статистика:\n────────────────────\n🔥 Всего дней в сериях: {total}\n👥 Активных связей: {len(rows)}")


# --- ИНЛАЙН РЕЖИМ ---
@dp.inline_query()
async def inline_handler(query: InlineQuery):
    track_user(query.from_user)
    uid = query.from_user.id
    results = [
        InlineQueryResultArticle(
            id="fire", title="⚡ Продлить огонёк", thumbnail_url=FIRE_ICON,
            input_message_content=InputTextMessageContent(message_text="✨ Нажми кнопку ниже, чтобы продлить серию 🔥"),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="✅ Продлить", callback_data=f"acc_{uid}")]])
        ),
        InlineQueryResultArticle(
            id="check", title="🏆 Сколько дней?", thumbnail_url=STATS_ICON,
            input_message_content=InputTextMessageContent(message_text="📊 Нажми кнопку, чтобы проверить огонёк"),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="📊 Показать дни", callback_data=f"show_{uid}")]])
        )
    ]
    await query.answer(results, cache_time=1, is_personal=True)


# --- ЛОГИКА КНОПОК ---
@dp.callback_query(F.data.startswith("acc_"))
async def process_acc(callback: types.CallbackQuery):
    sender_id = int(callback.data.split("_")[1])
    receiver_id = callback.from_user.id
    if sender_id == receiver_id:
        await callback.answer("❌ Это твой вызов!", show_alert=True);
        return

    key = f"{min(sender_id, receiver_id)}_{max(sender_id, receiver_id)}"
    today = datetime.now().date()
    conn = sqlite3.connect('series_final.db')
    cursor = conn.cursor()
    cursor.execute('SELECT streak, last_date, saves FROM series WHERE key = ?', (key,))
    row = cursor.fetchone()

    if row:
        streak, last_date_str, saves = row
        last_date = datetime.strptime(last_date_str, '%Y-%m-%d').date()
        if last_date == today:
            await callback.answer()
            await bot.edit_message_text(text="✨ Огонёк уже продлен",
                                        inline_message_id=callback.inline_message_id)
            return
        new_streak = streak + 1 if last_date == today - timedelta(days=1) else 1
    else:
        new_streak, saves = 1, 3

    cursor.execute('INSERT OR REPLACE INTO series (key, streak, last_date, notified, saves) VALUES (?, ?, ?, 0, ?)',
                   (key, new_streak, today.strftime('%Y-%m-%d'), saves))
    conn.commit();
    conn.close()
    await callback.answer()
    await bot.edit_message_text(f"🔥 Огонёк продлён!\n────────────────────\n📈 Текущая серия: {new_streak} дн.",
                                inline_message_id=callback.inline_message_id)


@dp.callback_query(F.data.startswith("res_"))
async def process_restore(callback: types.CallbackQuery):
    key = callback.data.replace("res_", "")
    today = datetime.now().date()
    conn = sqlite3.connect('series_final.db')
    cursor = conn.cursor()
    cursor.execute('SELECT streak, saves FROM series WHERE key = ?', (key,))
    row = cursor.fetchone()

    if row and row[1] > 0:
        streak, saves = row
        new_saves = saves - 1
        cursor.execute('UPDATE series SET last_date = ?, saves = ?, notified = 0 WHERE key = ?',
                       (today.strftime('%Y-%m-%d'), new_saves, key))
        conn.commit()
        await callback.message.edit_text(
            f"💎 Серия восстановлена!\n────────────────────\n🔥 Прогресс: {streak} дн.\n✨ Осталось попыток: {new_saves}")
    else:
        await callback.answer("❌ Попытки закончились", show_alert=True)
    conn.close()


@dp.callback_query(F.data.startswith("show_"))
async def process_show(callback: types.CallbackQuery):
    sender_id = int(callback.data.split("_")[1])
    key = f"{min(sender_id, callback.from_user.id)}_{max(sender_id, callback.from_user.id)}"
    conn = sqlite3.connect('series_final.db')
    cursor = conn.cursor()
    cursor.execute('SELECT streak FROM series WHERE key = ?', (key,))
    row = cursor.fetchone()
    conn.close()
    await callback.answer()
    await bot.edit_message_text(f"🔥 Ваша совместная серия: {row[0] if row else 0} дн.",
                                inline_message_id=callback.inline_message_id)


async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(check_dead_streaks())
    await asyncio.gather(start_webserver(), dp.start_polling(bot))


if __name__ == '__main__':
    asyncio.run(main())
