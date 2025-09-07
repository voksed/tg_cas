import asyncio
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.functions.payments import GetSavedStarGiftsRequest, GetPaymentFormRequest, SendStarsFormRequest
from telethon.tl.types import InputPeerUser, InputSavedStarGiftUser, InputInvoiceStarGiftTransfer
import config

async def send_any_gift(client: TelegramClient, username: str) -> dict:
    """
    Отправляет первый доступный NFT-подарок указанному пользователю.

    Args:
        client (TelegramClient): Активный клиент Telethon.
        username (str): Имя пользователя Telegram (с '@') для отправки подарка.

    Returns:
        dict: Результат операции {'success': bool, 'slug': str или None, 'error': str или None}.
    """
    try:
        me = await client.get_me()

        saved = await client(GetSavedStarGiftsRequest(
            peer=InputPeerUser(user_id=me.id, access_hash=me.access_hash),
            offset="",
            limit=100
        ))

        if not saved.gifts:
            raise Exception("No saved gifts available")

        matched = saved.gifts[0]
        slug = getattr(matched.gift, "slug", "unknown")

        peer = await client.get_input_entity(username)

        invoice = InputInvoiceStarGiftTransfer(
            stargift=InputSavedStarGiftUser(msg_id=matched.msg_id),
            to_id=peer
        )

        form = await client(GetPaymentFormRequest(invoice=invoice))
        await client(SendStarsFormRequest(form_id=form.form_id, invoice=invoice))

        return {"success": True, "slug": slug, "error": None}

    except FloodWaitError as e:
        await asyncio.sleep(e.seconds)
        return await send_any_gift(client, username)

    except Exception as e:
        return {"success": False, "slug": None, "error": str(e)}