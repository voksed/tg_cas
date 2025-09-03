from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, BaseFilter
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter
from aiogram import BaseMiddleware
import asyncio
from datetime import datetime, timedelta
import re
import json
import os
from config import *

TOKEN = TELEGRAM_TOKEN
ADMIN_IDS = TELEGRAM_ADMIN_IDS
GROUP_ID = TELEGRAM_GROUP_ID  # Числовой ID публичной группы
DATA_FILE = "slot_data.json"

bot = Bot(token=TOKEN)
dp = Dispatcher()

is_slot_active = False
total_spins = 0
last_admin_message = {}
command_message_ids = []  # Список для хранения ID сообщений с командами

class RateLimitMiddleware(BaseMiddleware):
    """Middleware to handle TelegramRetryAfter exceptions."""
    async def __call__(self, handler, event, data):
        while True:
            try:
                return await handler(event, data)
            except TelegramRetryAfter as e:
                retry_after = e.retry_after + 1  # Add 1 second buffer
                await asyncio.sleep(retry_after)
                continue  # Retry the request after the delay

class SlotCommandFilter(BaseFilter):
    """Custom filter for slot commands."""
    async def __call__(self, message: Message) -> bool:
        if not message.text:
            return False
        return bool(re.match(r"^(?:/spin|!крутить|крутить|🎰)(?:@\w+)?$", message.text, re.IGNORECASE))

def load_slot_data() -> None:
    """Загружает параметры слота из файла JSON."""
    global is_slot_active, total_spins
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as file:
                data = json.load(file)
                is_slot_active = data.get("is_slot_active", False)
                total_spins = data.get("total_spins", 0)
        except Exception:
            pass

def save_slot_data() -> None:
    """Сохраняет параметры слота в файл JSON."""
    try:
        with open(DATA_FILE, 'w') as file:
            json.dump({
                "is_slot_active": is_slot_active,
                "total_spins": total_spins
            }, file, indent=4)
    except Exception:
        pass

def get_admin_keyboard() -> InlineKeyboardMarkup:
    """Создает инлайн-клавиатуру для админской панели."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Активировать слот" if not is_slot_active else "Деактивировать слот",
            callback_data="toggle_slot"
        )],
        [InlineKeyboardButton(text="Показать статистику", callback_data="show_stats"),
         InlineKeyboardButton(text="Шпаргалка", callback_data="show_help")]
    ])

def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь админом."""
    return user_id in ADMIN_IDS

def get_slot_status() -> str:
    """Возвращает текущий статус слота."""
    return "активирован" if is_slot_active else "деактивирован"

async def delete_message(chat_id: int, message_id: int) -> None:
    """Пытается удалить сообщение и обрабатывает ошибки."""
    try:
        await bot.delete_message(chat_id, message_id)
        if chat_id == GROUP_ID:
            command_message_ids.append(message_id)
    except TelegramBadRequest:
        pass

async def clear_command_messages() -> None:
    """Удаляет сообщения с командами из command_message_ids."""
    global command_message_ids
    for message_id in command_message_ids:
        try:
            await bot.delete_message(GROUP_ID, message_id)
        except TelegramBadRequest:
            continue
    command_message_ids = []
    await notify_admins("Команды успешно очищены.")

async def notify_admins(message: str) -> None:
    """Отправляет сообщение всем админам."""
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, message)
        except (TelegramForbiddenError, Exception):
            pass

async def mute_chat(chat_id: int) -> None:
    """Мьютит чат на 5 минут при джекпоте."""
    try:
        await bot.set_chat_permissions(
            chat_id=chat_id,
            permissions={
                "can_send_messages": False,
                "can_send_media_messages": False,
                "can_send_polls": False,
                "can_send_other_messages": False,
                "can_add_web_page_previews": False
            },
            until_date=datetime.now() + timedelta(minutes=5)
        )
        await bot.send_message(chat_id, "Чат замьючен на 5 минут из-за джекпота!")
    except Exception:
        await notify_admins("Ошибка при мьюте чата.")

async def update_admin_panel(admin_id: int, status: str, message_id: int) -> None:
    """Обновляет панель админа с новым текстом и клавиатурой."""
    new_text = f"Слот {status}!\nОбщее количество круток: {total_spins}"
    try:
        await bot.edit_message_text(
            chat_id=admin_id,
            message_id=message_id,
            text=new_text,
            reply_markup=get_admin_keyboard()
        )
        last_admin_message[admin_id] = {"text": new_text, "message_id": message_id}
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error):
            pass

@dp.message(Command("start"))
async def start_command(message: Message) -> None:
    """Обрабатывает команду /start."""
    welcome_text = (
        "🎰 Добро пожаловать в бот-слот!\n"
        "Используйте команды /spin, !крутить, крутить или 🎰 для игры в слот.\n"
        f"Текущий статус слота: {get_slot_status()}."
    )
    await message.answer(welcome_text)

@dp.message(Command("admin"))
async def admin_panel(message: Message) -> None:
    """Открывает админскую панель для управления слотом."""
    if is_admin(message.from_user.id):
        status = get_slot_status()
        keyboard = get_admin_keyboard()
        response = await message.answer(
            f"Панель управления слотом:\nСлот {status}!\nОбщее количество круток: {total_spins}",
            reply_markup=keyboard
        )
        last_admin_message[message.from_user.id] = {
            "text": f"Слот {status}!\nОбщее количество круток: {total_spins}",
            "message_id": response.message_id
        }
    await delete_message(message.chat.id, message.message_id)

@dp.callback_query(F.data == "toggle_slot")
async def toggle_slot(callback_query) -> None:
    """Переключает состояние слота и обновляет админскую панель."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("У вас нет прав для этого действия!")
        return

    global is_slot_active
    is_slot_active = not is_slot_active
    status = get_slot_status()
    new_text = f"Слот {status}!\nОбщее количество круток: {total_spins}"

    admin_id = callback_query.from_user.id
    if admin_id in last_admin_message and last_admin_message[admin_id]["text"] == new_text:
        await callback_query.answer(f"Слот уже {status}.")
        return

    try:
        await callback_query.message.edit_text(new_text, reply_markup=get_admin_keyboard())
        last_admin_message[admin_id] = {"text": new_text, "message_id": callback_query.message.message_id}
        await callback_query.answer(f"Слот {status}.")
    except TelegramBadRequest as error:
        if "message is not modified" in str(error):
            await callback_query.answer(f"Слот уже {status}.")
        else:
            raise error

    if not is_slot_active:
        await clear_command_messages()

@dp.callback_query(F.data == "show_stats")
async def show_stats(callback_query) -> None:
    """Показывает статистику круток слота."""
    if is_admin(callback_query.from_user.id):
        await callback_query.answer(f"Общее количество круток: {total_spins}")
    else:
        await callback_query.answer("У вас нет прав для этого действия!")

@dp.callback_query(F.data == "show_help")
async def show_help(callback_query) -> None:
    """Показывает шпаргалку для админов."""
    if is_admin(callback_query.from_user.id):
        help_text = (
            f"📋 /admin - панель, /spin, !крутить/крутить/🎰 - слот. "
            f"Команды и лишние сообщения удаляются при активном слоте. "
            f"Статус: {get_slot_status()}, круток: {total_spins}"
        )
        await callback_query.answer(text=help_text, show_alert=True)
    else:
        await callback_query.answer("У вас нет прав для этого действия!")

@dp.message(SlotCommandFilter())
async def spin_slot(message: Message) -> None:
    """Обрабатывает команды /spin, !крутить, крутить или 🎰 для игры в слот."""
    global is_slot_active, total_spins

    if message.chat.type in ["group", "supergroup"] and not is_slot_active:
        await delete_message(message.chat.id, message.message_id)
        return

    if message.chat.type in ["group", "supergroup"] and message.chat.id != GROUP_ID:
        await delete_message(message.chat.id, message.message_id)
        return

    if message.chat.type in ["group", "supergroup"]:
        total_spins += 1
        save_slot_data()

    user_ref = (
        f"@{message.from_user.username}"
        if message.from_user.username
        else f'<a href="tg://user?id={message.from_user.id}">Игрок</a>'
    )

    dice_message = await message.answer_dice(emoji="🎰")
    value = dice_message.dice.value

    is_win = False
    if value == 64:
        await asyncio.sleep(1.5)
        result = f"💎 {user_ref}, ДЖЕКПОТ!"
        is_win = True
        if message.chat.type in ["group", "supergroup"]:
            await mute_chat(message.chat.id)
    else:
        await asyncio.sleep(1.5)
        result = f"😔 {user_ref}, проигрыш"

    await message.answer(result, parse_mode="HTML")
    await delete_message(message.chat.id, message.message_id)

    if is_win and message.chat.type in ["group", "supergroup"]:
        admin_message = f"Пользователь {user_ref} сыграл в слот. Результат: {result}\nОбщее количество круток: {total_spins}"
        await notify_admins(admin_message)

@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def delete_non_bot_messages(message: Message) -> None:
    """Удаляет все сообщения в группе, кроме команд и ответов бота, если слот активен."""
    if message.chat.id != GROUP_ID or not is_slot_active:
        return

    # Проверяем, является ли сообщение командой для бота
    is_command = (
        message.text and
        re.match(r"^(?:/start|/spin|!крутить|крутить|🎰)(?:@\w+)?$", message.text, re.IGNORECASE)
    )

    # Проверяем, является ли сообщение ответом бота
    is_bot_message = message.from_user.id == bot.id

    # Удаляем сообщение, если оно не команда и не от бота
    if not (is_command or is_bot_message):
        await delete_message(message.chat.id, message.message_id)

async def main() -> None:
    """Запускает бота и начинает обработку сообщений."""
    print("Бот запущен!")
    load_slot_data()
    dp.message.middleware(RateLimitMiddleware())  # Register the rate limit middleware
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())