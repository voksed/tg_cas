from telethon import TelegramClient, events

# ====== Настройки ======
api_id = 21186855
api_hash = "ce42502b7e0e79619f6f81607f56fb22"
telephone = "+998902813121"

# ====== Создаём клиента ======
client = TelegramClient("echo_bot", api_id, api_hash)
client.start(phone=telephone)

# ====== Хэндлер сообщений ======
@client.on(events.NewMessage)
async def handler(event):
    if event.is_private:  # только личные сообщения
        await event.reply(f"Все говорят {event.message.message}, а ты купи слона!")

# ====== Запуск ======
print("Бот запущен...")
client.run_until_disconnected()
