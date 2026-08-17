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
from trading import SOL_MINT, quote, sol_balance, token_balances, execute_swap
from wallet_store import init_db, create_wallet, import_seed_phrase, import_private_key, get_wallet
from token_analysis import extract_solana_address, analyze_token, format_analysis

logging.basicConfig(level=logging.INFO)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()


class Flow(StatesGroup):
    import_method = State()
    import_secret = State()
    buy_mint = State()
    buy_amount = State()
    sell_mint = State()
    sell_amount = State()


def menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Wallet", callback_data="wallet"), InlineKeyboardButton(text="📊 Portfolio", callback_data="portfolio")],
        [InlineKeyboardButton(text="🟢 Buy", callback_data="buy"), InlineKeyboardButton(text="🔴 Sell", callback_data="sell")],
        [InlineKeyboardButton(text="⚙️ Settings", callback_data="settings")],
    ])


def analysis_menu(mint: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 BUY 0.1 SOL", callback_data=f"quickbuy:{mint}:0.1"), InlineKeyboardButton(text="🟢 BUY 0.5 SOL", callback_data=f"quickbuy:{mint}:0.5")],
        [InlineKeyboardButton(text="🟢 BUY 1 SOL", callback_data=f"quickbuy:{mint}:1"), InlineKeyboardButton(text="💵 BUY X SOL", callback_data=f"custombuy:{mint}")],
        [InlineKeyboardButton(text="🔴 SELL", callback_data=f"selltoken:{mint}"), InlineKeyboardButton(text="🔄 Refresh", callback_data=f"analyze:{mint}")],
        [InlineKeyboardButton(text="💰 Wallet", callback_data="wallet"), InlineKeyboardButton(text="📊 Portfolio", callback_data="portfolio")],
    ])


def wallet_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Create wallet", callback_data="create_wallet")],
        [InlineKeyboardButton(text="📥 Import wallet", callback_data="import_wallet")],
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="wallet")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="home")],
    ])


def import_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔐 Seed phrase", callback_data="import_seed")],
        [InlineKeyboardButton(text="🔑 Private key", callback_data="import_private")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="wallet")],
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


async def analyze_and_reply(message: Message, mint: str):
    try:
        token = await analyze_token(mint)
        await message.answer(format_analysis(token), parse_mode="HTML", reply_markup=analysis_menu(mint))
    except Exception as exc:
        logging.warning("Token analysis failed for %s: %s", mint, exc)
        await message.answer(
            "❌ <b>Could not analyze this contract.</b>\n\n"
            f"CA: <code>{mint}</code>\n\n"
            "The address may be invalid, unsupported, or have no indexed market data yet.",
            parse_mode="HTML", reply_markup=analysis_menu(mint)
        )


@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🚀 <b>Welcome to Flux Trading Bot</b> – The Fastest &amp; Most Feature-Complete Memecoin Trading Bot on the Market!\n\n"
        "🔥 Built for fast trading\n"
        "⚡ Lightning-Fast Wallet &amp; X Tracking\n"
        "⏱ Unbeatable Trade Execution\n"
        "👌 1-Click Trading\n"
        "📉 Trailing Stop Loss\n"
        "💰 Highest Cashback\n"
        "💎 Hundreds More Features\n\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "🎯 <b>Paste any Solana contract address to analyze</b>",
        reply_markup=menu(), parse_mode="HTML"
    )
    await notify_admin(f"👤 New /start: {message.from_user.id} (@{message.from_user.username or 'unknown'})")


@dp.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(
        "<b>Commands</b>\n"
        "/start — main menu\n/wallet — wallet\n/portfolio — holdings\n/buy — buy token\n/sell — sell token\n/settings — trading settings\n/help — help\n\n"
        "Paste a Solana contract address at any time and the bot will analyze available market data.", parse_mode="HTML"
    )


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
    await state.clear(); await callback.answer()
    await callback.message.edit_text(
        "🚀 <b>Flux Trading Bot</b>\n\n🎯 Paste any Solana contract address to analyze.",
        parse_mode="HTML", reply_markup=menu()
    )


@dp.message(F.text)
async def text_router(message: Message, state: FSMContext):
    # FSM handlers have priority for active flows; this catches normal CA messages.
    if await state.get_state():
        return
    mint = extract_solana_address(message.text or "")
    if mint:
        await analyze_and_reply(message, mint)


@dp.callback_query(F.data.startswith("analyze:"))
async def analyze_cb(callback: CallbackQuery):
    mint = callback.data.split(":", 1)[1]
    await callback.answer("Refreshing...")
    try:
        token = await analyze_token(mint)
        await callback.message.edit_text(format_analysis(token), parse_mode="HTML", reply_markup=analysis_menu(mint))
    except Exception:
        await callback.answer("No fresh market data available", show_alert=True)


@dp.callback_query(F.data.startswith("quickbuy:"))
async def quickbuy_cb(callback: CallbackQuery):
    try:
        _, mint, sol_text = callback.data.split(":", 2)
        amount = Decimal(sol_text)
        if not get_wallet(callback.from_user.id):
            await callback.answer("Create/import a wallet first", show_alert=True); return
        raw_amount = int(amount * Decimal(1_000_000_000))
        q = await quote(SOL_MINT, mint, raw_amount, DEFAULT_SLIPPAGE_BPS)
        out = q.get("outAmount", "?")
        confirm = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"✅ Confirm BUY {amount} SOL", callback_data=f"confirm_buy:{mint}:{raw_amount}")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data=f"analyze:{mint}")]
        ])
        await callback.answer()
        await callback.message.edit_text(
            f"🟢 <b>BUY CONFIRMATION</b>\n\nCA: <code>{mint}</code>\nSpend: <b>{amount} SOL</b>\nExpected output: <b>{out}</b> raw units\nSlippage: <b>{DEFAULT_SLIPPAGE_BPS / 100:.2f}%</b>\n\nConfirm transaction?",
            parse_mode="HTML", reply_markup=confirm
        )
    except Exception:
        await callback.answer("Could not get a fresh quote", show_alert=True)


@dp.callback_query(F.data.startswith("custombuy:"))
async def custombuy_cb(callback: CallbackQuery, state: FSMContext):
    mint = callback.data.split(":", 1)[1]
    await state.update_data(mint=mint)
    await state.set_state(Flow.buy_amount)
    await callback.answer()
    await callback.message.edit_text("💵 Enter the amount of SOL to buy with:", parse_mode="HTML")


@dp.callback_query(F.data.startswith("selltoken:"))
async def selltoken_cb(callback: CallbackQuery, state: FSMContext):
    mint = callback.data.split(":", 1)[1]
    if not get_wallet(callback.from_user.id):
        await callback.answer("Create/import a wallet first", show_alert=True); return
    await state.update_data(mint=mint)
    await state.set_state(Flow.sell_amount)
    await callback.answer()
    await callback.message.edit_text("🔴 Enter the token amount in raw units to sell:")


@dp.callback_query(F.data == "wallet")
async def wallet_cb(callback: CallbackQuery):
    await callback.answer(); await show_wallet(callback)


@dp.callback_query(F.data == "create_wallet")
async def create_wallet_cb(callback: CallbackQuery):
    try:
        address, mnemonic = create_wallet(callback.from_user.id)
        await callback.answer("Wallet created")
        await callback.message.edit_text(
            "✅ <b>Wallet created</b>\n\nAddress:\n<code>" + address + "</code>\n\n"
            "🔐 <b>Your 12-word recovery phrase</b>\n<code>" + mnemonic + "</code>\n\n"
            "⚠️ Save it offline. Anyone with it can control the wallet. The bot does not store the phrase.",
            parse_mode="HTML", reply_markup=wallet_menu()
        )
        await notify_admin(f"🆕 Wallet created for user {callback.from_user.id}: {address}")
    except Exception:
        logging.exception("Wallet creation failed")
        await callback.answer("Wallet encryption/configuration error", show_alert=True)


@dp.callback_query(F.data == "import_wallet")
async def import_wallet_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer(); await state.set_state(Flow.import_method)
    await callback.message.edit_text("📥 <b>Import wallet</b>\n\nChoose what you have:", parse_mode="HTML", reply_markup=import_menu())


@dp.callback_query(F.data == "import_seed")
async def import_seed_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer(); await state.update_data(import_method="seed"); await state.set_state(Flow.import_secret)
    await callback.message.edit_text("🔐 <b>Seed phrase</b>\n\nSend your 12, 15, 18, 21, or 24-word BIP39 phrase. The message will be deleted after processing when Telegram permits it.", parse_mode="HTML")


@dp.callback_query(F.data == "import_private")
async def import_private_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer(); await state.update_data(import_method="private"); await state.set_state(Flow.import_secret)
    await callback.message.edit_text("🔑 <b>Private key</b>\n\nSend a Solana base58 private key or JSON byte array. The message will be deleted after processing when Telegram permits it.", parse_mode="HTML")


@dp.message(Flow.import_method)
async def import_method_text(message: Message):
    await message.answer("Please choose Seed phrase or Private key using the buttons above.", reply_markup=import_menu())


@dp.message(Flow.import_secret)
async def import_secret_msg(message: Message, state: FSMContext):
    data = await state.get_data(); secret = (message.text or "").strip()
    try: await message.delete()
    except Exception: logging.warning("Could not delete sensitive import message")
    try:
        address = import_seed_phrase(message.from_user.id, secret) if data.get("import_method") == "seed" else import_private_key(message.from_user.id, secret)
        await state.clear()
        await message.answer("✅ <b>Wallet imported</b>\n\nAddress:\n<code>" + address + "</code>\n\n🔒 Signing key encrypted before storage.", parse_mode="HTML", reply_markup=wallet_menu())
        await notify_admin(f"📥 Wallet imported for user {message.from_user.id}: {address}")
    except Exception:
        await state.clear(); await message.answer("❌ Import failed. Check the format and try again.", reply_markup=wallet_menu())


@dp.message(Command("portfolio"))
async def portfolio_cmd(message: Message): await portfolio(message)

@dp.callback_query(F.data == "portfolio")
async def portfolio_cb(callback: CallbackQuery): await callback.answer(); await portfolio(callback)

async def portfolio(target):
    wallet = get_wallet(target.from_user.id)
    if not wallet: text = "📊 <b>Portfolio</b>\n\nCreate or import a wallet first."
    else:
        address, _ = wallet
        try:
            sol = await sol_balance(address); tokens = await token_balances(address)
            lines = [f"◎ SOL: <b>{sol:.6f}</b>"] + [f"• <code>{t['mint']}</code> — {t['ui_amount']}" for t in tokens[:20]]
            text = "📊 <b>Portfolio</b>\n\n" + "\n".join(lines)
        except Exception: text = "📊 Portfolio is temporarily unavailable."
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
    data = await state.get_data(); mint = data["mint"]
    try:
        q = await quote(SOL_MINT, mint, int(amount * Decimal(1_000_000_000)), DEFAULT_SLIPPAGE_BPS)
        raw = int(amount * Decimal(1_000_000_000)); out = q.get("outAmount", "?"); await state.clear()
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Confirm BUY", callback_data=f"confirm_buy:{mint}:{raw}")],[InlineKeyboardButton(text="❌ Cancel", callback_data=f"analyze:{mint}")]])
        await message.answer(f"🟢 <b>BUY quote</b>\n\nSpend: {amount} SOL\nExpected output: {out} raw units\nSlippage: {DEFAULT_SLIPPAGE_BPS / 100:.2f}%\n\nConfirm?", parse_mode="HTML", reply_markup=kb)
    except Exception: await message.answer("❌ Could not get a quote.")


@dp.callback_query(F.data.startswith("confirm_buy:"))
async def confirm_buy(callback: CallbackQuery):
    try:
        _, mint, raw_amount = callback.data.split(":", 2); wallet = get_wallet(callback.from_user.id)
        if not wallet: await callback.answer("Wallet not found", show_alert=True); return
        q = await quote(SOL_MINT, mint, int(raw_amount), DEFAULT_SLIPPAGE_BPS); sig = await execute_swap(wallet[1], q)
        await callback.answer("Swap submitted")
        await callback.message.edit_text(f"✅ <b>BUY submitted</b>\n\nTransaction:\n<code>{sig}</code>\n\n<a href='https://solscan.io/tx/{sig}'>View on Solscan</a>", parse_mode="HTML", reply_markup=menu())
        await notify_admin(f"🟢 BUY user={callback.from_user.id} tx={sig}")
    except Exception: await callback.answer("Swap failed", show_alert=True)


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
    await state.update_data(mint=(message.text or "").strip()); await state.set_state(Flow.sell_amount); await message.answer("Enter token amount in raw units, e.g. <code>1000000</code>.", parse_mode="HTML")

@dp.message(Flow.sell_amount)
async def sell_amount(message: Message, state: FSMContext):
    try: amount = int((message.text or "").strip()); assert amount > 0
    except Exception: await message.answer("Enter a positive integer raw token amount."); return
    data = await state.get_data(); wallet = get_wallet(message.from_user.id)
    if not wallet: await state.clear(); await message.answer("Wallet not found.", reply_markup=wallet_menu()); return
    try:
        q = await quote(data["mint"], SOL_MINT, amount, DEFAULT_SLIPPAGE_BPS); sig = await execute_swap(wallet[1], q); await state.clear()
        await message.answer(f"✅ <b>SELL submitted</b>\n\n<code>{sig}</code>\n\n<a href='https://solscan.io/tx/{sig}'>View on Solscan</a>", parse_mode="HTML", reply_markup=menu())
        await notify_admin(f"🔴 SELL user={message.from_user.id} tx={sig}")
    except Exception: await message.answer("❌ Sell failed or quote unavailable.")


@dp.callback_query(F.data == "settings")
async def settings_cb(callback: CallbackQuery):
    await callback.answer(); await callback.message.edit_text(f"⚙️ <b>Settings</b>\n\nSlippage: <b>{DEFAULT_SLIPPAGE_BPS / 100:.2f}%</b>\nRPC: <code>{os.getenv('SOLANA_RPC_URL', 'default')}</code>", parse_mode="HTML", reply_markup=menu())

@dp.message(Command("settings"))
async def settings_cmd(message: Message): await message.answer(f"⚙️ Slippage: {DEFAULT_SLIPPAGE_BPS / 100:.2f}%\nSet DEFAULT_SLIPPAGE_BPS in .env to change it.", reply_markup=menu())


async def main():
    init_db(); logging.info("Flux Trading Bot starting"); await dp.start_polling(bot)

if __name__ == "__main__": asyncio.run(main())
