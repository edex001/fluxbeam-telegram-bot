import re
import httpx

SOLANA_ADDRESS_RE = re.compile(r"(?<![1-9A-HJ-NP-Za-km-z])[1-9A-HJ-NP-Za-km-z]{32,44}(?![1-9A-HJ-NP-Za-km-z])")


def extract_solana_address(text: str) -> str | None:
    match = SOLANA_ADDRESS_RE.search(text or "")
    return match.group(0) if match else None


async def analyze_token(mint: str) -> dict:
    """Fetch public market data for a Solana mint from DexScreener.
    Missing fields are returned as None; the bot must not invent token metrics.
    """
    url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
    async with httpx.AsyncClient(timeout=12) as client:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()

    pairs = [p for p in data.get("pairs", []) if p.get("chainId") == "solana"]
    pairs.sort(key=lambda p: float(p.get("liquidity", {}).get("usd") or 0), reverse=True)
    pair = pairs[0] if pairs else {}
    base = pair.get("baseToken", {})
    txns = pair.get("txns", {}).get("h24", {})
    volume = pair.get("volume", {}).get("h24")
    liquidity = pair.get("liquidity", {}).get("usd")
    market_cap = pair.get("marketCap") or pair.get("fdv")

    return {
        "mint": mint,
        "name": base.get("name") or "Unknown token",
        "symbol": base.get("symbol") or "?",
        "price_usd": pair.get("priceUsd"),
        "liquidity_usd": liquidity,
        "market_cap_usd": market_cap,
        "volume_24h_usd": volume,
        "change_24h": pair.get("priceChange", {}).get("h24"),
        "buys_24h": txns.get("buys"),
        "sells_24h": txns.get("sells"),
        "dex": pair.get("dexId"),
        "url": pair.get("url"),
    }


def _money(value):
    if value is None:
        return "N/A"
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"${value / 1_000:.2f}K"
    return f"${value:.4f}"


def format_analysis(token: dict) -> str:
    change = token.get("change_24h")
    change_text = "N/A" if change is None else f"{float(change):+.2f}%"
    return (
        "🔎 <b>Token Analysis</b>\n\n"
        f"🪙 <b>{token['name']}</b> ({token['symbol']})\n"
        f"CA: <code>{token['mint']}</code>\n\n"
        f"💵 Price: <b>{_money(token.get('price_usd'))}</b>\n"
        f"💧 Liquidity: <b>{_money(token.get('liquidity_usd'))}</b>\n"
        f"📊 Market Cap/FDV: <b>{_money(token.get('market_cap_usd'))}</b>\n"
        f"📈 24h: <b>{change_text}</b>\n"
        f"📦 24h Volume: <b>{_money(token.get('volume_24h_usd'))}</b>\n"
        f"🟢 Buys: {token.get('buys_24h', 'N/A')}  🔴 Sells: {token.get('sells_24h', 'N/A')}\n"
        f"🏪 DEX: {token.get('dex') or 'N/A'}\n\n"
        "⚠️ <i>Market data is informational. Always verify the contract and token risk before trading.</i>"
    )
