import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is missing.")

MONGO_URL: str = os.getenv("MONGO_URL", "mongodb://localhost:27017")
PORT: int = int(os.getenv("PORT", 8000))

# Railway automatically supplies RAILWAY_PUBLIC_DOMAIN without http/https protocol
raw_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", f"localhost:{PORT}")
if not raw_domain.startswith("http://") and not raw_domain.startswith("https://"):
    BASE_URL: str = f"https://{raw_domain}"
else:
    BASE_URL: str = raw_domain
