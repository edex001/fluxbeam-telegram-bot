import asyncio
import os
import logging
from decimal import Decimal

import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
JUPITER_BASE_URL = os.getenv("JUPITER_BASE_URL", "https://api.jup.ag")
JUPITER_API_KEY = os.getenv("JUPITER_API_KEY", "")
FLUXBEAM_BASE_URL = os.getenv("FLUXBEAM_API_BASE_URL", "")
FLUXBEAM_API_KEY = os.getenv("FLUXBEAM_API_KEY", "")

SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()


def menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Wallet", callback_data="wallet"),
         InlineKeyboardButton(text="📊 Price", callback_data="price")],
        [InlineKeyboardButton(text="🔄 Swap", callback_data="swap"),
         InlineKeyboardButton(text="⚙️ Settings", callback_data="settings")],
        [InlineKeyboardButton(text="🌐 FluxBeam", url="https://fluxbeam.xyz/")],
    ])


async def notify_admin(text: str) -> None:
    if ADMIN_ID:
        try:
            await bot.send_message(int(ADMIN_ID), text)
        except Exception:
            logging.exception("Admin notification failed")


async def sol_price_usd() -> str:
    headers = {"x-api-key": JUPITER_API_KEY} if JUPITER_API_KEY else {}
    url = f"{JUPITER_BASE_URL}/price/v3"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, params={"ids": SOL_MINT}, headers=headers)
            r.raise_for_status()
            data = r.json()
            item = data.get(SOL_MINT, {})
            price = item.get("usdPrice") or item.get("price")
            return f"${float(price):,.4f}" if price else "Unavailable"
    except Exception:
        return "Unavailable"


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "⚡ <b>FluxBeam Trading Bot</b>\n\n"
        "A Telegram interface for Solana token discovery and trading.\n\n"
        "Choose an option below:",
        reply_markup=menu(), parse_mode="HTML",
    )
    await notify_admin(f"👤 /start from {message.from_user.id} (@{message.from_user.username or 'unknown'})")


@dp.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(
        "<b>Commands</b>\n"
        "/start — open the trading menu\n"
        "/price — SOL price\n"
        "/swap — swap flow\n"
        "/help — this help\n\n"
        "Keep all secrets in environment variables; never paste private keys into GitHub.",
        parse_mode="HTML",
    )


@dp.message(Command("price"))
async def price_cmd(message: Message):
    await message.answer(f"💵 <b>SOL price:</b> {await sol_price_usd()}", parse_mode="HTML")


@dp.callback_query(F.data == "price")
async def price_cb(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        f"💵 <b>SOL price:</b> {await sol_price_usd()}",
        parse_mode="HTML", reply_markup=menu()
    )


@dp.callback_query(F.data == "wallet")
async def wallet_cb(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "💰 <b>Wallet</b>\n\n"
        "Wallet management is intentionally separated from the Telegram UI. "
        "The production version should use an encrypted key store or an external signer.\n\n"
        "No private keys are stored in this repository.",
        parse_mode="HTML", reply_markup=menu()
    )


@dp.callback_query(F.data == "swap")
async def swap_cb(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "🔄 <b>Swap</b>\n\n"
        "The swap adapter is ready for the official FluxBeam API endpoint. "
        "Until that endpoint/key is configured, do not enable live trading.\n\n"
        "Default integration variables:\n"
        "<code>FLUXBEAM_API_BASE_URL</code>\n"
        "<code>FLUXBEAM_API_KEY</code>",
        parse_mode="HTML", reply_markup=menu()
    )


@dp.callback_query(F.data == "settings")
async def settings_cb(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "⚙️ <b>Settings</b>\n\n"
        "• Slippage: configurable in the trading adapter\n"
        "• RPC: SOLANA_RPC_URL\n"
        "• Admin alerts: ADMIN_ID\n"
        "• Jupiter API: JUPITER_BASE_URL / JUPITER_API_KEY\n"
        "• FluxBeam API: FLUXBEAM_API_BASE_URL / FLUXBEAM_API_KEY",
        parse_mode="HTML", reply_markup=menu()
    )


@dp.message(Command("swap"))
async def swap_cmd(message: Message):
    await message.answer(
        "🔄 Swap is not enabled for live execution yet. Configure the official FluxBeam API adapter first."
    )


async def main():
    logging.info("FluxBeam Telegram Bot starting")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
