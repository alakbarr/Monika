"""
Golden-set regression test untuk news classification.
Jalankan manual atau via cron mingguan: python -m tests.golden_news_classification
Isi GOLDEN_SET dengan contoh nyata yang sudah diverifikasi manual (title, summary, expected_impact).
Target: precision/recall per kelas >= 85% sebelum deploy perubahan prompt classification.
"""
import asyncio
import os
import sys

# Tambahkan trading-agent ke sys.path agar impor modul berhasil
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from analysis.prefetch.news_digest import NEWS_CLASSIFICATION_SCHEMA, NewsDigestProcessor
from config.settings import load_settings

GOLDEN_SET = [
    {"title": "US CPI comes in at 4.2% vs 3.1% forecast, biggest miss in 2 years",
     "summary": "Inflation data released moments ago...", "fetched_minutes_ago": 12,
     "calendar_prior": "high", "expected_impact": "BREAKING"},
    {"title": "Fed's Williams says rate path remains data dependent",
     "summary": "Routine comments from NY Fed president.", "fetched_minutes_ago": 30,
     "calendar_prior": None, "expected_impact": "HIGH"},
    {"title": "Gold surges past $2400 as dollar weakens",
     "summary": "Market reaction to overnight dollar weakness.", "fetched_minutes_ago": 25,
     "calendar_prior": None, "expected_impact": "HIGH"},  # bukan BREAKING — reaksi pasar, bukan event baru
    {"title": "Analysis: What CPI miss means for markets",
     "summary": "Opinion piece analyzing implications.", "fetched_minutes_ago": 40,
     "calendar_prior": None, "expected_impact": "MEDIUM"},
    # ... tambahkan minimal 50-100 contoh terverifikasi manual dari histori nyata
]

async def run_eval():
    settings = load_settings('config/settings.yaml')
    processor = NewsDigestProcessor(settings)
    correct, total = 0, 0
    confusion = {}
    for item in GOLDEN_SET:
        # Bangun prompt setara batch tunggal dan panggil classifier langsung
        # (adaptasi ringan dari classify_unscored_news untuk single-item eval)
        prompt = f"Current time: N/A\n1. TIME-IN-SYSTEM: {item['fetched_minutes_ago']} min ago\n   TITLE: {item['title']}\n   SUMMARY: {item['summary']}\n\nClassify."
        result = await processor._flash_lite.classify_json(prompt=prompt, schema=NEWS_CLASSIFICATION_SCHEMA)
        predicted = (result[0]['impact'] if result else 'ERROR')
        expected = item['expected_impact']
        total += 1
        if predicted == expected:
            correct += 1
        confusion.setdefault(expected, {}).setdefault(predicted, 0)
        confusion[expected][predicted] += 1
        print(f"[{'OK' if predicted==expected else 'MISS'}] expected={expected} got={predicted} :: {item['title'][:60]}")
    print(f"\nAccuracy: {correct}/{total} = {correct/total*100:.1f}%")
    print(f"Confusion matrix: {confusion}")
    if correct / total < 0.85:
        print("⚠️ ACCURACY BELOW 85% THRESHOLD — review prompt/few-shot examples before deploying changes.")

if __name__ == '__main__':
    import sys
    if sys.platform == "win32":
        asyncio.run(run_eval(), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(run_eval())
