import asyncio
import logging
import sqlite3
from aiohttp import web # Добавляем для Render
from aiogram import Bot, Dispatcher, types
# ... (остальные твои импорты) ...

API_TOKEN = '8708528114:AAE2o48onjYjZGrEGJXwPwZC3yYAVSwqI6k'
bot = Bot(token=API_TOKEN) # Прокси БОЛЬШЕ НЕ НУЖЕН!
dp = Dispatcher()

# --- МИНИ ВЕБ-СЕРВЕР ДЛЯ RENDER ---
async def handle(request):
    return web.Response(text="Bot is alive!")

async def start_webserver():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 10000) # Render использует порт 10000
    await site.start()

# --- ТВОИ ОБРАБОТЧИКИ (ОСТАВЛЯЕМ БЕЗ ИЗМЕНЕНИЙ) ---
# ... (весь код с инлайном, бд и командами) ...

async def main():
    init_db()
    # Запускаем веб-сервер и бота одновременно
    await asyncio.gather(
        start_webserver(),
        dp.start_polling(bot)
    )

if __name__ == '__main__':
    asyncio.run(main())
