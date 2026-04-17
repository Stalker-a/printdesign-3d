import json
import os
from pathlib import Path
from urllib import error, request


BASE_DIR = Path(__file__).resolve().parent


def load_env(env_path: Path) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_env(BASE_DIR / ".env")

token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

if not token:
    raise SystemExit("Укажите TELEGRAM_BOT_TOKEN в .env")

url = f"https://api.telegram.org/bot{token}/getUpdates"

try:
    with request.urlopen(url, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
except error.HTTPError as exc:
    details = exc.read().decode("utf-8", errors="ignore")
    raise SystemExit(f"Telegram API error: {details or exc.reason}") from exc

if not data.get("ok"):
    raise SystemExit(f"Telegram error: {data}")

results = data.get("result", [])
if not results:
    raise SystemExit("Нет обновлений. Сначала напишите вашему боту в Telegram, затем повторите команду.")

for update in results:
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    if chat:
        print(
            json.dumps(
                {
                    "chat_id": chat.get("id"),
                    "chat_type": chat.get("type"),
                    "username": chat.get("username"),
                    "first_name": chat.get("first_name"),
                    "title": chat.get("title"),
                },
                ensure_ascii=False,
            )
        )
