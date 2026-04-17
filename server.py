import json
import os
import sys
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error, parse, request


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


AI_PROVIDER = os.getenv("AI_PROVIDER", "openai").strip().lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini").strip()
HF_API_KEY = os.getenv("HF_API_KEY", "").strip()
HF_MODEL = os.getenv("HF_MODEL", "google/gemma-2-2b-it").strip()
CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
CLOUDFLARE_MODEL = os.getenv("CLOUDFLARE_MODEL", "@cf/openai/gpt-oss-20b").strip()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip().rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:4b").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
TELEGRAM_TARGET = os.getenv("TELEGRAM_TARGET", "@SHAKOTAN2").strip()
SITE_NAME = os.getenv("SITE_NAME", "PrintForge 3D").strip()
HOST = os.getenv("HOST", "0.0.0.0").strip()
PORT = int(os.getenv("PORT", "8000"))


def json_response(handler, status: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def read_json(handler):
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0:
        raise ValueError("Пустое тело запроса.")

    raw_body = handler.rfile.read(length)
    try:
        return json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Некорректный JSON.") from exc


def extract_text_from_response(data: dict) -> str:
    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    parts = []
    for item in data.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"}:
                text = content.get("text", "")
                if text:
                    parts.append(text)

    return "\n".join(part.strip() for part in parts if part.strip())


def build_assistant_instructions() -> str:
    return (
        f"Ты AI-консультант сайта {SITE_NAME}. "
        "Отвечай на русском языке кратко, профессионально и дружелюбно. "
        "Тематика: 3D-печать деталей, 3D-сканирование, реверс-инжиниринг, материалы, сроки и расчет. "
        "Если данных мало, задай 1-3 уточняющих вопроса. "
        "Если запрос похож на заявку, мягко попроси контакт и кратко перечисли, что нужно для расчета. "
        "Не придумывай невозможные сроки и цены."
    )


def normalize_history(history: list[dict], user_message: str) -> list[dict]:
    instructions = (
        build_assistant_instructions()
    )

    input_messages = []
    for item in history[-10:]:
        role = item.get("role")
        content = str(item.get("content", "")).strip()
        if role in {"user", "assistant"} and content:
            input_messages.append({"role": role, "content": content})

    if not input_messages or input_messages[-1].get("role") != "user":
        input_messages.append({"role": "user", "content": user_message})

    if not input_messages or input_messages[0].get("role") != "system":
        input_messages.insert(0, {"role": "system", "content": instructions})

    return input_messages


def extract_hf_text(data: dict) -> str:
    choices = data.get("choices", [])
    if not choices:
        return ""

    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()
    return ""


def call_openai(history: list[dict], user_message: str) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("Не задан OPENAI_API_KEY в .env")

    payload = {
        "model": OPENAI_MODEL,
        "instructions": build_assistant_instructions(),
        "input": normalize_history(history, user_message)[1:],
    }

    req = request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"OpenAI API error: {details or exc.reason}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"OpenAI недоступен: {exc.reason}") from exc

    text = extract_text_from_response(data)
    if not text:
        raise RuntimeError("OpenAI вернул пустой ответ.")
    return text


def call_huggingface(history: list[dict], user_message: str) -> str:
    if not HF_API_KEY:
        raise RuntimeError("Не задан HF_API_KEY в .env")

    messages = normalize_history(history, user_message)
    payload = {
        "model": HF_MODEL,
        "messages": messages,
    }

    req = request.Request(
        "https://router.huggingface.co/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {HF_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Hugging Face API error: {details or exc.reason}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Hugging Face недоступен: {exc.reason}") from exc

    text = extract_hf_text(data)
    if not text:
        raise RuntimeError("Hugging Face вернул пустой ответ.")
    return text


def call_cloudflare(history: list[dict], user_message: str) -> str:
    if not CLOUDFLARE_ACCOUNT_ID or not CLOUDFLARE_API_TOKEN:
        raise RuntimeError("Не заданы CLOUDFLARE_ACCOUNT_ID или CLOUDFLARE_API_TOKEN в .env")

    payload = {
        "model": CLOUDFLARE_MODEL,
        "input": normalize_history(history, user_message),
    }

    req = request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Cloudflare AI error: {details or exc.reason}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Cloudflare AI недоступен: {exc.reason}") from exc

    result = data.get("result", {})
    text = extract_text_from_response(result) if isinstance(result, dict) else ""
    if not text and isinstance(result, str):
        text = result.strip()
    if not text:
        text = extract_text_from_response(data)
    if not text:
        raise RuntimeError("Cloudflare AI вернул пустой ответ.")
    return text


def call_ollama(history: list[dict], user_message: str) -> str:
    messages = normalize_history(history, user_message)
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
    }

    req = request.Request(
        f"{OLLAMA_BASE_URL}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer ollama",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Ollama API error: {details or exc.reason}") from exc
    except error.URLError as exc:
        raise RuntimeError(
            "Ollama недоступен. Установите Ollama, запустите его и скачайте модель."
        ) from exc

    text = extract_hf_text(data)
    if not text:
        raise RuntimeError("Ollama вернул пустой ответ.")
    return text


def generate_ai_reply(history: list[dict], user_message: str) -> str:
    if AI_PROVIDER == "openai":
        return call_openai(history, user_message)
    if AI_PROVIDER == "huggingface":
        return call_huggingface(history, user_message)
    if AI_PROVIDER == "cloudflare":
        return call_cloudflare(history, user_message)
    if AI_PROVIDER == "ollama":
        return call_ollama(history, user_message)

    raise RuntimeError("Неподдерживаемый AI_PROVIDER. Используйте openai, huggingface, cloudflare или ollama.")


def send_telegram_message(text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN:
        return False

    target = TELEGRAM_CHAT_ID or TELEGRAM_TARGET
    if not target:
        return False

    payload = parse.urlencode(
        {
            "chat_id": target,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")

    req = request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        data=payload,
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Telegram API error: {details or exc.reason}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Telegram недоступен: {exc.reason}") from exc

    if not data.get("ok"):
        raise RuntimeError(f"Telegram error: {data}")

    return True


def format_chat_alert(user_message: str, ai_reply: str) -> str:
    return (
        "<b>Новое обращение из AI-чата</b>\n"
        f"<b>Сайт:</b> {SITE_NAME}\n\n"
        f"<b>Сообщение клиента:</b>\n{html_escape(user_message)}\n\n"
        f"<b>Ответ AI:</b>\n{html_escape(ai_reply)}"
    )


def format_contact_alert(name: str, contact: str, task: str) -> str:
    return (
        "<b>Новая заявка с сайта</b>\n"
        f"<b>Сайт:</b> {SITE_NAME}\n\n"
        f"<b>Имя:</b> {html_escape(name or 'Не указано')}\n"
        f"<b>Контакт:</b> {html_escape(contact or 'Не указан')}\n\n"
        f"<b>Задача:</b>\n{html_escape(task or 'Пусто')}"
    )


def html_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


class ApiHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def do_POST(self):
        if self.path == "/api/chat":
            self.handle_chat()
            return
        if self.path == "/api/contact":
            self.handle_contact()
            return

        json_response(self, HTTPStatus.NOT_FOUND, {"error": "Маршрут не найден."})

    def handle_chat(self):
        try:
            payload = read_json(self)
            message = str(payload.get("message", "")).strip()
            history = payload.get("history") or []

            if not message:
                raise ValueError("Введите сообщение для ассистента.")

            reply = generate_ai_reply(history, message)

            telegram_sent = False
            try:
                telegram_sent = send_telegram_message(format_chat_alert(message, reply))
            except RuntimeError as exc:
                print(f"[telegram chat warning] {exc}", file=sys.stderr)

            json_response(
                self,
                HTTPStatus.OK,
                {"reply": reply, "telegram_sent": telegram_sent},
            )
        except ValueError as exc:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except RuntimeError as exc:
            json_response(self, HTTPStatus.BAD_GATEWAY, {"error": str(exc)})
        except Exception as exc:
            json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"Внутренняя ошибка: {exc}"})

    def handle_contact(self):
        try:
            payload = read_json(self)
            name = str(payload.get("name", "")).strip()
            contact = str(payload.get("contact", "")).strip()
            task = str(payload.get("task", "")).strip()

            if not task:
                raise ValueError("Опишите задачу перед отправкой.")
            if not contact:
                raise ValueError("Укажите телефон или Telegram для обратной связи.")

            telegram_sent = send_telegram_message(format_contact_alert(name, contact, task))
            if not telegram_sent:
                raise RuntimeError("Не настроен TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID.")

            json_response(
                self,
                HTTPStatus.OK,
                {"message": "Заявка отправлена в Telegram.", "telegram_sent": telegram_sent},
            )
        except ValueError as exc:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except RuntimeError as exc:
            json_response(self, HTTPStatus.BAD_GATEWAY, {"error": str(exc)})
        except Exception as exc:
            json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"Внутренняя ошибка: {exc}"})


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), ApiHandler)
    print(f"Server started: http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    main()
