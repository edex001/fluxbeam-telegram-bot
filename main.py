import asyncio
import logging
import os
from decimal import Decimal

import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from dotenv import load_dotenv

load_dotenv()
from config import BOT_TOKEN, ADMIN_ID, DEFAULT_SLIPPAGE_BPS
from trading import SOL_MINT, quote, sol_balance, token_balances, execute_swap, sol_balance
from wallet_store import init_db, create_wallet, import_wallet, get_wallet

logging.basicConfig(level=logging.INFO)
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

class Flow(StatesGroup):
    import_key = State()
    buy_mint = State()
    buy_amount = State()
    sell_mint = State()
    sell_amount = State()


def menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Wallet", callback_data="wallet"), InlineKeyboardButton(text="📊 Portfolio", callback_data="portfolio")],
        [InlineKeyboardButton(text="🟢 Buy", callback_data="buy"), InlineKeyboardButton(text="🔴 Sell", callback_data="sell")],
        [InlineKeyboardButton(text="⚙️ Settings", callback_data="settings")],
        [InlineKeyboardButton(text="🌐 FluxBeam", url="https://fluxbeam.xyz/")],
    ])


def wallet_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Create wallet", callback_data="create_wallet")],
        [InlineKeyboardButton(text="📥 Import wallet", callback_data="import_wallet")],
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="wallet")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="home")],
    ])

async def notify_admin(text):
    if ADMIN_ID:
        try:
            await bot.send_message(int(ADMIN_ID), text)
        except Exception:
            logging.exception("Admin notification failed")

async def sol_price():
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get("https://api.jup.ag/price/v3", params={"ids": SOL_MINT})
            r.raise_for_status()
            item = r.json().get(SOL_MINT, {})
            return float(item.get("usdPrice") or item.get("price"))
    except Exception:
        return None

@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("⚡ <b>FluxBeam Trading Bot</b>\n\nTrade Solana tokens directly from Telegram.\n\nCreate or import a wallet to get started.", reply_markup=menu(), parse_mode="HTML")
    await notify_admin(f"👤 New /start: {message.from_user.id} (@{message.from_user.username or 'unknown'})")

@dp.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer("<b>Commands</b>\n/start — main menu\n/wallet — wallet\n/portfolio — holdings\n/buy — buy token\n/sell — sell token\n/settings — trading settings\n/help — help", parse_mode="HTML")

@dp.message(Command("wallet"))
async def wallet_cmd(message: Message):
    await show_wallet(message)

async def show_wallet(target):
    user_id = target.from_user.id
    wallet = get_wallet(user_id)
    if not wallet:
        text = "💰 <b>Wallet</b>\n\nNo wallet linked yet."
    else:
        address, _ = wallet
        try:
            balance = await sol_balance(address)
            text = f"💰 <b>Wallet</b>\n\n<code>{address}</code>\n\n◎ SOL: <b>{balance:.6f}</b>"
        except Exception:
            text = f"💰 <b>Wallet</b>\n\n<code>{address}</code>\n\n◎ SOL: unavailable"
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, parse_mode="HTML", reply_markup=wallet_menu())
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=wallet_menu())

@dp.callback_query(F.data == "home")
async def home_cb(callback: CallbackQuery, state: FSMContext):
    await state.clear(); await callback.answer(); await callback.message.edit_text("⚡ <b>FluxBeam Trading Bot</b>\n\nChoose an action:", parse_mode="HTML", reply_markup=menu())

@dp.callback_query(F.data == "wallet")
async def wallet_cb(callback: CallbackQuery):
    await callback.answer(); await show_wallet(callback)

@dp.callback_query(F.data == "create_wallet")
async def create_wallet_cb(callback: CallbackQuery):
    try:
        address = create_wallet(callback.from_user.id)
        await callback.answer("Wallet created")
        await callback.message.edit_text("✅ <b>Wallet created</b>\n\nAddress:\n<code>" + address + "</code>\n\n⚠️ Your encrypted wallet is stored locally. Back up your secret securely before using real funds.", parse_mode="HTML", reply_markup=wallet_menu())
        await notify_admin(f"🆕 Wallet created for user {callback.from_user.id}: {address}")
    except Exception as exc:
        await callback.answer("Wallet encryption is not configured", show_alert=True)
        logging.exception(exc)

@dp.callback_query(F.data == "import_wallet")
async def import_wallet_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer(); await state.set_state(Flow.import_key)
    await callback.message.edit_text("📥 <b>Import wallet</b>\n\nSend your Solana private key as a base58 string or JSON byte array.\n\n⚠️ Never send a key in a public chat. Delete the message after import.", parse_mode="HTML")

@dp.message(Flow.import_key)
async def import_key_msg(message: Message, state: FSMContext):
    try:
        address = import_wallet(message.from_user.id, message.text or "")
        await state.clear(); await message.delete()
        await message.answer("✅ Wallet imported.\n\n<code>" + address + "</code>", parse_mode="HTML", reply_markup=wallet_menu())
        await notify_admin(f"📥 Wallet imported for user {message.from_user.id}: {address}")
    except Exception:
        await message.answer("❌ Invalid Solana private key. Try again or /start to cancel.")

@dp.message(Command("portfolio"))
async def portfolio_cmd(message: Message):
    await portfolio(message)

@dp.callback_query(F.data == "portfolio")
async def portfolio_cb(callback: CallbackQuery):
    await callback.answer(); await portfolio(callback)

async def portfolio(target):
    wallet = get_wallet(target.from_user.id)
    if not wallet:
        text = "📊 <b>Portfolio</b>\n\nCreate or import a wallet first."
    else:
        address, _ = wallet
        try:
            sol = await sol_balance(address)
            tokens = await token_balances(address)
            lines = [f"◎ SOL: <b>{sol:.6f}</b>"]
            for token in tokens[:20]: lines.append(f"• <code>{token['mint']}</code> — {token['ui_amount']}")
            text = "📊 <b>Portfolio</b>\n\n" + "\n".join(lines)
        except Exception as exc:
            logging.exception(exc); text = "📊 Portfolio is temporarily unavailable."
    if isinstance(target, CallbackQuery): await target.message.edit_text(text, parse_mode="HTML", reply_markup=menu())
    else: await target.answer(text, parse_mode="HTML", reply_markup=menu())

@dp.message(Command("price"))
async def price_cmd(message: Message):
    p = await sol_price(); await message.answer(f"💵 SOL: <b>${p:,.4f}</b>" if p else "SOL price unavailable", parse_mode="HTML")

@dp.callback_query(F.data == "buy")
async def buy_cb(callback: CallbackQuery, state: FSMContext):
    if not get_wallet(callback.from_user.id): await callback.answer("Create/import a wallet first", show_alert=True); return
    await callback.answer(); await state.set_state(Flow.buy_mint); await callback.message.edit_text("🟢 <b>Buy</b>\n\nSend the token mint address:", parse_mode="HTML")

@dp.message(Command("buy"))
async def buy_cmd(message: Message, state: FSMContext):
    if not get_wallet(message.from_user.id): await message.answer("Create/import a wallet first.", reply_markup=wallet_menu()); return
    await state.set_state(Flow.buy_mint); await message.answer("🟢 Send the token mint address:")

@dp.message(Flow.buy_mint)
async def buy_mint(message: Message, state: FSMContext):
    await state.update_data(mint=(message.text or "").strip()); await state.set_state(Flow.buy_amount); await message.answer("How much SOL do you want to spend? Example: <code>0.1</code>", parse_mode="HTML")

@dp.message(Flow.buy_amount)
async def buy_amount(message: Message, state: FSMContext):
    try: amount = Decimal((message.text or "").strip()); assert amount > 0
    except Exception: await message.answer("Enter a positive SOL amount."); return
    data = await state.get_data(); wallet = get_wallet(message.from_user.id)
    try:
        q = await quote(SOL_MINT, data["mint"], int(amount * Decimal(1_000_000_000)), DEFAULT_SLIPPAGE_BPS)
        out = q.get("outAmount", "?")
        await state.clear()
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Confirm BUY", callback_data=f"confirm_buy:{data['mint']}:{int(amount*Decimal(1_000_000_000))}")],[InlineKeyboardButton(text="❌ Cancel", callback_data="home")]])
        await message.answer(f"🟢 <b>BUY quote</b>\n\nSpend: {amount} SOL\nExpected output: {out} raw units\nSlippage: {DEFAULT_SLIPPAGE_BPS/100:.2f}%\n\nConfirm?", parse_mode="HTML", reply_markup=kb)
    except Exception as exc: logging.exception(exc); await message.answer("❌ Could not get a quote. Check the mint address/API configuration.")

@dp.callback_query(F.data.startswith("confirm_buy:"))
async def confirm_buy(callback: CallbackQuery):
    try:
        _, mint, raw_amount = callback.data.split(":", 2); wallet = get_wallet(callback.from_user.id); q = await quote(SOL_MINT, mint, int(raw_amount), DEFAULT_SLIPPAGE_BPS); sig = await execute_swap(wallet[1], q)
        await callback.answer("Swap submitted")
        await callback.message.edit_text(f"✅ <b>BUY submitted</b>\n\nTransaction:\n<code>{sig}</code>\n\n<a href='https://solscan.io/tx/{sig}'>View on Solscan</a>", parse_mode="HTML", reply_markup=menu())
        await notify_admin(f"🟢 BUY user={callback.from_user.id} tx={sig}")
    except Exception as exc: logging.exception(exc); await callback.answer("Swap failed", show_alert=True)

@dp.callback_query(F.data == "sell")
async def sell_cb(callback: CallbackQuery, state: FSMContext):
    if not get_wallet(callback.from_user.id): await callback.answer("Create/import a wallet first", show_alert=True); return
    await callback.answer(); await state.set_state(Flow.sell_mint); await callback.message.edit_text("🔴 <b>Sell</b>\n\nSend the token mint address:", parse_mode="HTML")

@dp.message(Command("sell"))
async def sell_cmd(message: Message, state: FSMContext):
    if not get_wallet(message.from_user.id): await message.answer("Create/import a wallet first."); return
    await state.set_state(Flow.sell_mint); await message.answer("🔴 Send the token mint address:")

@dp.message(Flow.sell_mint)
async def sell_mint(message: Message, state: FSMContext):
    await state.update_data(mint=(message.text or "").strip()); await state.set_state(Flow.sell_amount); await message.answer("Enter token amount in UI units, e.g. <code>1000000</code> raw units.", parse_mode="HTML")

@dp.message(Flow.sell_amount)
async def sell_amount(message: Message, state: FSMContext):
    try: amount = int((message.text or "").strip()); assert amount > 0
    except Exception: await message.answer("Enter a positive integer raw token amount."); return
    data = await state.get_data(); wallet = get_wallet(message.from_user.id)
    try:
        q = await quote(data["mint"], SOL_MINT, amount, DEFAULT_SLIPPAGE_BPS); sig = await execute_swap(wallet[1], q); await state.clear()
        await message.answer(f"✅ <b>SELL submitted</b>\n\n<code>{sig}</code>\n\n<a href='https://solscan.io/tx/{sig}'>View on Solscan</a>", parse_mode="HTML", reply_markup=menu())
        await notify_admin(f"🔴 SELL user={message.from_user.id} tx={sig}")
    except Exception as exc: logging.exception(exc); await message.answer("❌ Sell failed or quote unavailable.")

@dp.callback_query(F.data == "settings")
async def settings_cb(callback: CallbackQuery):
    await callback.answer(); await callback.message.edit_text(f"⚙️ <b>Settings</b>\n\nSlippage: <b>{DEFAULT_SLIPPAGE_BPS/100:.2f}%</b>\nRPC: <code>{os.getenv('SOLANA_RPC_URL','default')}</code>\nAdmin notifications: {'enabled' if ADMIN_ID else 'disabled'}\n\nChange these through environment variables before deployment.", parse_mode="HTML", reply_markup=menu())

@dp.message(Command("settings"))
async def settings_cmd(message: Message):
    await message.answer(f"⚙️ Slippage: {DEFAULT_SLIPPAGE_BPS/100:.2f}%\nSet DEFAULT_SLIPPAGE_BPS in .env to change it.", reply_markup=menu())

async def main():
    init_db()
    logging.info("FluxBeam Telegram Bot starting")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
