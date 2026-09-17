import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load env from trading-agent/.env or root .env
env_path = Path("trading-agent/.env")
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()

token = os.getenv("HF_TOKEN")

print("==================================================")
print("  Google TimesFM 3.0 Model Weights Downloader     ")
print("==================================================")
if token:
    print("[HF] Authenticated access token detected.")
else:
    print("[HF] Note: HF_TOKEN not found in environment, proceeding anonymously.")

repo_id = "google/timesfm-3.0-pytorch"
print(f"[HF] Downloading model repository '{repo_id}' (~1.32 GB)...")
print("[HF] Please wait while weights are downloaded to local cache...")

try:
    from huggingface_hub import snapshot_download
    cache_dir = snapshot_download(
        repo_id=repo_id,
        token=token if token else None,
    )
    print(f"[HF] Download completed successfully!")
    print(f"[HF] Cached local path: {cache_dir}")

    # Verify model initialization
    print("\n[TimesFM] Verifying model initialization from cached weights...")
    import timesfm
    model = timesfm.TimesFM3Forecaster.from_pretrained(repo_id)
    print("[TimesFM] Model initialized successfully!")
    print(f"[TimesFM] Quantiles: {model.config.quantiles}")
    print("\n[SUCCESS] Google TimesFM 3.0 is ready for live neural inference!")

except Exception as e:
    print(f"\n[ERROR] Download or initialization failed: {e}", file=sys.stderr)
    sys.exit(1)
