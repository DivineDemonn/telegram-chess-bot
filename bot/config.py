import os
import sys
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    print("FATAL ERROR: BOT_TOKEN environment variable is missing.")
    sys.exit(1)

MONGO_URL: str = os.getenv("MONGO_URL", "mongodb://localhost:27017").strip()
PORT: int = int(os.getenv("PORT", 10000))

# Render injects RENDER_EXTERNAL_URL automatically for Web Services
raw_url = os.getenv("RENDER_EXTERNAL_URL", f"http://localhost:{PORT}").strip()
if raw_url.startswith("http://") or raw_url.startswith("https://"):
    BASE_URL: str = raw_url
else:
    BASE_URL: str = f"https://{raw_url}"
