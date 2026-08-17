import os
import base64
import httpx
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction

SOL_MINT = "So11111111111111111111111111111111111111112"
JUPITER_BASE_URL = os.getenv("JUPITER_BASE_URL", "https://api.jup.ag")
JUPITER_API_KEY = os.getenv("JUPITER_API_KEY", "")
RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")


def headers():
    return {"x-api-key": JUPITER_API_KEY} if JUPITER_API_KEY else {}


async def rpc(method: str, params: list):
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(RPC_URL, json={"jsonrpc":"2.0","id":1,"method":method,"params":params})
        r.raise_for_status()
        data = r.json()
        if data.get("error"):
            raise RuntimeError(str(data["error"]))
        return data["result"]


async def sol_balance(address: str) -> float:
    result = await rpc("getBalance", [address, {"commitment":"confirmed"}])
    return result["value"] / 1_000_000_000


async def token_balances(address: str):
    result = await rpc("getTokenAccountsByOwner", [address, {"programId":"TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"}, {"encoding":"jsonParsed","commitment":"confirmed"}])
    items = []
    for item in result.get("value", []):
        info = item["account"]["data"]["parsed"]["info"]
        amount = info["tokenAmount"]
        if int(amount.get("amount", "0")):
            items.append({"mint": info["mint"], "ui_amount": amount.get("uiAmount", 0), "decimals": amount.get("decimals", 0)})
    return items


async def quote(input_mint: str, output_mint: str, amount: int, slippage_bps: int = 100):
    url = f"{JUPITER_BASE_URL}/swap/v1/quote"
    params = {"inputMint":input_mint,"outputMint":output_mint,"amount":amount,"slippageBps":slippage_bps}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url, params=params, headers=headers())
        r.raise_for_status()
        return r.json()


async def execute_swap(user_keypair: Keypair, quote_response: dict):
    url = f"{JUPITER_BASE_URL}/swap/v1/swap"
    payload = {"quoteResponse": quote_response, "userPublicKey": str(user_keypair.pubkey()), "dynamicComputeUnitLimit": True, "prioritizationFeeLamports": "auto"}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, json=payload, headers={**headers(), "content-type":"application/json"})
        r.raise_for_status()
        data = r.json()
    raw = base64.b64decode(data["swapTransaction"])
    unsigned = VersionedTransaction.from_bytes(raw)
    signed = VersionedTransaction(unsigned.message, [user_keypair])
    result = await rpc("sendTransaction", [base64.b64encode(bytes(signed)).decode(), {"encoding":"base64","skipPreflight":False,"maxRetries":3}])
    return result
