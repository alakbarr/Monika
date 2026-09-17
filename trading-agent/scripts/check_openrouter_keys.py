"""
Skrip Verifikasi dan Ping Test Multi-Key OpenRouter (Tanpa Menampilkan Kunci Lengkap).
Memeriksa:
1. Nama variable env yang terdeteksi
2. Jumlah key yang ada
3. Validitas koneksi dan otentikasi masing-masing key (Masked)
"""
import os
import sys
import time
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# Load .env dari root trading-agent atau root project
env_path = Path(__file__).resolve().parent.parent / ".env"
if not env_path.exists():
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Tambahkan direktori trading-agent ke sys.path
trading_agent_dir = str(Path(__file__).resolve().parent.parent)
if trading_agent_dir not in sys.path:
    sys.path.insert(0, trading_agent_dir)

from openai import AsyncOpenAI
from utils.api.openrouter_rate_limiter import (
    get_paid_key,
    get_free_keys,
    get_all_keys,
    is_free_tier_model
)

def mask_key(k: str) -> str:
    if not k:
        return "<EMPTY>"
    if len(k) < 12:
        return f"{k[:3]}...{k[-2:]}"
    return f"{k[:8]}...{k[-4:]}"

async def ping_key(api_key: str, model: str, key_label: str):
    masked = mask_key(api_key)
    client = AsyncOpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        timeout=30.0,
        default_headers={
            "HTTP-Referer": "https://tradeagent.local",
            "X-Title": "AI Trading Agent Key Verifier",
        }
    )
    t0 = time.time()
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5,
            temperature=0.0
        )
        dur = (time.time() - t0) * 1000
        content = resp.choices[0].message.content if resp.choices else "OK"
        clean_content = content.replace("\n", " ").strip()[:20] if content else "OK"
        return True, dur, f"200 OK (latency: {dur:.0f}ms, reply: '{clean_content}')"
    except Exception as e:
        dur = (time.time() - t0) * 1000
        err_msg = str(e)
        if api_key in err_msg:
            err_msg = err_msg.replace(api_key, masked)
        return False, dur, f"FAILED: {err_msg}"

async def main():
    paid_key = get_paid_key()
    free_keys = get_free_keys()
    legacy_key = os.getenv("OPENROUTER_API_KEY")
    all_keys = get_all_keys()

    print("=" * 65)
    print(" OPENROUTER MULTI-KEY AUDIT & CONNECTIVITY TEST")
    print("=" * 65)
    
    # 1. Audit Variable Names
    has_paid_var = bool(os.getenv("OPENROUTER_PAID_API_KEY"))
    has_free_var = bool(os.getenv("OPENROUTER_API_KEYS"))
    has_legacy_var = bool(legacy_key)

    print("1. DETEKSI NAMA VARIABEL ENV:")
    print(f"   • OPENROUTER_PAID_API_KEY : {'[TERSEDIA]' if has_paid_var else '[TIDAK DISET]'}")
    print(f"   • OPENROUTER_API_KEYS      : {'[TERSEDIA]' if has_free_var else '[TIDAK DISET]'}")
    print(f"   • OPENROUTER_API_KEY (Leg) : {'[TERSEDIA]' if has_legacy_var else '[TIDAK DISET]'}")

    # 2. Key Count Summary
    print(f"\n2. JUMLAH KUNCI TERDETEKSI:")
    print(f"   • Total Kunci Unik : {len(all_keys)} kunci")
    print(f"   • Kunci Paid Tier  : {'1 kunci (' + mask_key(paid_key) + ')' if paid_key else '0 kunci'}")
    print(f"   • Kunci Free Tier  : {len(free_keys)} kunci")
    for idx, fk in enumerate(free_keys, 1):
        print(f"       - Free Key #{idx}: {mask_key(fk)}")
    print("=" * 65)

    if not all_keys:
        print("\n[ERROR] Tidak ada API key OpenRouter yang ditemukan di .env!")
        print("Silakan set OPENROUTER_PAID_API_KEY dan/atau OPENROUTER_API_KEYS di file .env.")
        return

    # 3. Connectivity / Ping Test
    free_test_model = "openrouter/free"
    print(f"\n3. PING TEST KUNCI FREE TIER (Model: '{free_test_model}'):")
    if free_keys:
        for idx, key in enumerate(free_keys, 1):
            label = f"Free Key #{idx}"
            ok, dur, detail = await ping_key(key, free_test_model, label)
            tag = "[PASS]" if ok else "[FAIL]"
            print(f"   {tag} {label} ({mask_key(key)}): {detail}")
    else:
        print("   (Tidak ada kunci khusus free tier di OPENROUTER_API_KEYS)")

    print(f"\n4. PING TEST KUNCI PAID TIER ({mask_key(paid_key)}):")
    if paid_key:
        # Test Free Route with Paid Key
        ok_free, _, detail_free = await ping_key(paid_key, free_test_model, "Paid Key (Free Route)")
        tag_free = "[PASS]" if ok_free else "[FAIL]"
        print(f"   {tag_free} Jalur Model Gratis ('{free_test_model}') : {detail_free}")

        # Test Paid Route (Lightweight model: google/gemini-2.5-flash / meta-llama/llama-3.2-1b-instruct)
        paid_test_model = "google/gemini-2.5-flash"
        ok_paid, _, detail_paid = await ping_key(paid_key, paid_test_model, "Paid Key (Paid Route)")
        tag_paid = "[PASS]" if ok_paid else "[FAIL]"
        print(f"   {tag_paid} Jalur Model Berbayar ('{paid_test_model}'): {detail_paid}")
    else:
        print("   (Kunci Paid Tier tidak dikonfigurasi)")

    print("\n" + "=" * 65)
    print(" HASIL AUDIT SELESAI")
    print("=" * 65)

if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(main())
