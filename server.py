import json
import os
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.parser import BytesParser
from email.policy import default
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error, parse, request


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
ANALYTICS_DIR = DATA_DIR / "analytics"
EVENT_LOG_PATH = ANALYTICS_DIR / "events.jsonl"


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


def env_flag(name: str, default: str = "1") -> bool:
    return os.getenv(name, default).strip().lower() not in {"0", "false", "no", "off"}


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
LEADS_TELEGRAM_BOT_TOKEN = os.getenv("LEADS_TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN).strip()
LEADS_TELEGRAM_CHAT_ID = os.getenv("LEADS_TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID).strip()
LEADS_TELEGRAM_TARGET = os.getenv("LEADS_TELEGRAM_TARGET", TELEGRAM_TARGET).strip()
SITE_NAME = os.getenv("SITE_NAME", "3d_design").strip()
HOST = os.getenv("HOST", "0.0.0.0").strip()
PORT = int(os.getenv("PORT", "8000"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", "10485760"))
INTERNAL_ANALYTICS_ENABLED = env_flag("INTERNAL_ANALYTICS_ENABLED", "1")
METRICS_TOKEN = os.getenv("METRICS_TOKEN", "").strip()

MAX_JSON_BYTES = 256 * 1024
MAX_FORM_BYTES = MAX_UPLOAD_BYTES + 512 * 1024
TRACK_EVENT_RE = re.compile(r"^[a-z_]{3,48}$")


@dataclass
class UploadedFile:
    filename: str
    content_type: str
    content: bytes

    @property
    def size(self) -> int:
        return len(self.content)


def iso_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def json_response(handler, status: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def read_request_body(handler, max_bytes: int) -> bytes:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0:
        raise ValueError("Пустое тело запроса.")
    if length > max_bytes:
        raise ValueError(f"Размер запроса превышает допустимый лимит {max_bytes // (1024 * 1024)} МБ.")
    return handler.rfile.read(length)


def read_json(handler, max_bytes: int = MAX_JSON_BYTES):
    raw_body = read_request_body(handler, max_bytes=max_bytes)
    try:
        return json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Некорректный JSON.") from exc


def read_multipart_form(handler) -> tuple[dict, UploadedFile | None]:
    content_type = handler.headers.get("Content-Type", "")
    if "multipart/form-data" not in content_type.lower():
        raise ValueError("Ожидалась форма с файлом.")

    raw_body = read_request_body(handler, max_bytes=MAX_FORM_BYTES)
    parser = BytesParser(policy=default)
    message = parser.parsebytes(
        (
            f"Content-Type: {content_type}\r\n"
            "MIME-Version: 1.0\r\n"
            "\r\n"
        ).encode("utf-8")
        + raw_body
    )

    fields: dict[str, str] = {}
    upload: UploadedFile | None = None

    for part in message.iter_parts():
        field_name = part.get_param("name", header="content-disposition")
        if not field_name:
            continue

        raw_content = part.get_payload(decode=True) or b""
        filename = part.get_filename()
        if filename:
            safe_name = sanitize_filename(filename)
            if not safe_name:
                continue
            if len(raw_content) > MAX_UPLOAD_BYTES:
                raise ValueError(
                    f"Файл слишком большой. Прикрепляйте файлы не больше {MAX_UPLOAD_BYTES // (1024 * 1024)} МБ."
                )

            upload = UploadedFile(
                filename=safe_name,
                content_type=part.get_content_type() or "application/octet-stream",
                content=raw_content,
            )
            continue

        charset = part.get_content_charset() or "utf-8"
        fields[field_name] = raw_content.decode(charset, errors="ignore").strip()

    return fields, upload


def read_contact_submission(handler) -> tuple[dict, UploadedFile | None]:
    content_type = handler.headers.get("Content-Type", "").lower()
    if content_type.startswith("application/json"):
        payload = read_json(handler)
        fields = {
            "name": str(payload.get("name", "")).strip(),
            "contact": str(payload.get("contact", "")).strip(),
            "task": str(payload.get("task", "")).strip(),
        }
        return fields, None

    if content_type.startswith("multipart/form-data"):
        return read_multipart_form(handler)

    raise ValueError("Неподдерживаемый формат формы. Используйте JSON или multipart/form-data.")


def clip_text(text: str, limit: int) -> str:
    cleaned = str(text).strip()
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 1].rstrip()}…"


def sanitize_filename(filename: str) -> str:
    basename = Path(filename).name.replace("\x00", "").strip()
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", basename)
    return safe_name[:96].strip("._-")


def save_uploaded_file(upload: UploadedFile, lead_id: str) -> dict:
    ensure_directory(UPLOAD_DIR)
    stored_name = f"{lead_id.lower()}-{upload.filename}"
    target_path = UPLOAD_DIR / stored_name
    target_path.write_bytes(upload.content)
    return {
        "filename": upload.filename,
        "stored_name": stored_name,
        "content_type": upload.content_type,
        "size": upload.size,
        "path": str(target_path.relative_to(BASE_DIR)).replace("\\", "/"),
    }


def append_jsonl(path: Path, payload: dict) -> None:
    ensure_directory(path.parent)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def anonymize_ip(ip_address: str) -> str:
    value = ip_address.strip()
    if not value:
        return ""
    if ":" in value:
        parts = value.split(":")
        return ":".join(parts[:4] + ["0000"] * max(0, 8 - len(parts[:4])))
    if "." in value:
        parts = value.split(".")
        if len(parts) == 4:
            return ".".join(parts[:3] + ["0"])
    return value


def get_client_ip(handler) -> str:
    forwarded = handler.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return handler.client_address[0] if handler.client_address else ""


def request_context(handler) -> dict:
    return {
        "path": handler.path,
        "client_ip": anonymize_ip(get_client_ip(handler)),
        "referer": clip_text(handler.headers.get("Referer", ""), 180),
        "user_agent": clip_text(handler.headers.get("User-Agent", ""), 180),
    }


def sanitize_event_details(details) -> dict:
    if not isinstance(details, dict):
        return {}

    safe_details = {}
    for raw_key, raw_value in list(details.items())[:12]:
        key = re.sub(r"[^a-z0-9_]+", "_", str(raw_key).strip().lower())[:40]
        if not key:
            continue
        if isinstance(raw_value, bool):
            safe_details[key] = raw_value
            continue
        if isinstance(raw_value, (int, float)):
            safe_details[key] = raw_value
            continue
        safe_details[key] = clip_text(raw_value, 120)
    return safe_details


def track_event(event: str, payload: dict) -> None:
    if not INTERNAL_ANALYTICS_ENABLED:
        return
    append_jsonl(
        EVENT_LOG_PATH,
        {
            "timestamp": iso_utc_now(),
            "event": event,
            **payload,
        },
    )


def parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def build_metrics_snapshot() -> dict:
    now = datetime.now(timezone.utc)
    last_7_days = now - timedelta(days=7)
    last_30_days = now - timedelta(days=30)
    summary = {
        "page_views": 0,
        "assistant_prompts": 0,
        "assistant_replies": 0,
        "leads_total": 0,
        "leads_with_file": 0,
        "leads_last_7_days": 0,
        "leads_last_30_days": 0,
    }
    recent_leads = []

    if not EVENT_LOG_PATH.exists():
        return {
            "generated_at": iso_utc_now(),
            "summary": summary,
            "recent_leads": recent_leads,
        }

    with EVENT_LOG_PATH.open("r", encoding="utf-8") as file:
        for raw_line in file:
            line = raw_line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue

            event = item.get("event")
            timestamp = parse_timestamp(str(item.get("timestamp", "")))

            if event == "page_view":
                summary["page_views"] += 1
                continue
            if event == "assistant_prompt":
                summary["assistant_prompts"] += 1
                continue
            if event == "assistant_reply":
                summary["assistant_replies"] += 1
                continue
            if event != "lead_submitted":
                continue

            summary["leads_total"] += 1
            if item.get("has_file"):
                summary["leads_with_file"] += 1
            if timestamp and timestamp >= last_7_days:
                summary["leads_last_7_days"] += 1
            if timestamp and timestamp >= last_30_days:
                summary["leads_last_30_days"] += 1

            recent_leads.append(
                {
                    "timestamp": item.get("timestamp"),
                    "lead_id": item.get("lead_id"),
                    "source": item.get("source"),
                    "has_file": item.get("has_file", False),
                    "telegram_sent": item.get("telegram_sent", False),
                }
            )

    recent_leads.sort(key=lambda item: item.get("timestamp") or "", reverse=True)
    return {
        "generated_at": iso_utc_now(),
        "summary": summary,
        "recent_leads": recent_leads[:10],
    }


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
    input_messages = []
    for item in history[-10:]:
        role = item.get("role")
        content = str(item.get("content", "")).strip()
        if role in {"user", "assistant"} and content:
            input_messages.append({"role": role, "content": content})

    if not input_messages or input_messages[-1].get("role") != "user":
        input_messages.append({"role": "user", "content": user_message})

    if not input_messages or input_messages[0].get("role") != "system":
        input_messages.insert(0, {"role": "system", "content": build_assistant_instructions()})

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

    payload = {
        "model": HF_MODEL,
        "messages": normalize_history(history, user_message),
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
    payload = {
        "model": OLLAMA_MODEL,
        "messages": normalize_history(history, user_message),
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
        raise RuntimeError("Ollama недоступен. Установите Ollama, запустите его и скачайте модель.") from exc

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


def html_escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def telegram_target() -> str:
    return LEADS_TELEGRAM_CHAT_ID or LEADS_TELEGRAM_TARGET


def build_multipart_body(fields: dict, files: list[dict]) -> tuple[str, bytes]:
    boundary = f"----PrintForge{uuid.uuid4().hex}"
    body = bytearray()

    for field_name, value in fields.items():
        if value is None:
            continue
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{field_name}"\r\n\r\n'.encode("utf-8"))
        body.extend(str(value).encode("utf-8"))
        body.extend(b"\r\n")

    for file_item in files:
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            (
                f'Content-Disposition: form-data; name="{file_item["field_name"]}"; '
                f'filename="{file_item["filename"]}"\r\n'
            ).encode("utf-8")
        )
        body.extend(f'Content-Type: {file_item["content_type"]}\r\n\r\n'.encode("utf-8"))
        body.extend(file_item["content"])
        body.extend(b"\r\n")

    body.extend(f"--{boundary}--\r\n".encode("utf-8"))
    return boundary, bytes(body)


def telegram_request(api_method: str, fields: dict, files: list[dict] | None = None) -> bool:
    if not LEADS_TELEGRAM_BOT_TOKEN:
        return False

    target = telegram_target()
    if not target:
        return False

    payload_fields = {"chat_id": target, **fields}
    headers = {}

    if files:
        boundary, body = build_multipart_body(payload_fields, files)
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    else:
        body = parse.urlencode(payload_fields).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    req = request.Request(
        f"https://api.telegram.org/bot{LEADS_TELEGRAM_BOT_TOKEN}/{api_method}",
        data=body,
        headers=headers,
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


def send_telegram_message(text: str) -> bool:
    return telegram_request(
        "sendMessage",
        {
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        },
    )


def send_telegram_document(upload: UploadedFile, lead_id: str) -> bool:
    return telegram_request(
        "sendDocument",
        {"caption": f"Файл по заявке {lead_id}"},
        files=[
            {
                "field_name": "document",
                "filename": upload.filename,
                "content_type": upload.content_type,
                "content": upload.content,
            }
        ],
    )


def format_chat_alert(user_message: str, ai_reply: str) -> str:
    return (
        "<b>Новое обращение из AI-чата</b>\n"
        f"<b>Сайт:</b> {SITE_NAME}\n\n"
        f"<b>Сообщение клиента:</b>\n{html_escape(user_message)}\n\n"
        f"<b>Ответ AI:</b>\n{html_escape(ai_reply)}"
    )


def format_contact_alert(lead_id: str, name: str, contact: str, task: str, upload_meta: dict | None) -> str:
    file_line = (
        f"<b>Файл:</b> {html_escape(upload_meta['filename'])} "
        f"({upload_meta['size'] // 1024} КБ)\n"
        if upload_meta
        else ""
    )
    return (
        "<b>Новая заявка с сайта</b>\n"
        f"<b>Сайт:</b> {SITE_NAME}\n"
        f"<b>Лид:</b> {lead_id}\n\n"
        f"<b>Имя:</b> {html_escape(name or 'Не указано')}\n"
        f"<b>Контакт:</b> {html_escape(contact or 'Не указан')}\n"
        f"{file_line}\n"
        f"<b>Задача:</b>\n{html_escape(task or 'Пусто')}"
    )


class ApiHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def do_GET(self):
        parsed = parse.urlparse(self.path)
        if parsed.path == "/api/metrics":
            self.handle_metrics(parsed)
            return
        super().do_GET()

    def do_POST(self):
        parsed = parse.urlparse(self.path)
        if parsed.path == "/api/chat":
            self.handle_chat()
            return
        if parsed.path == "/api/contact":
            self.handle_contact()
            return
        if parsed.path == "/api/track":
            self.handle_track()
            return

        json_response(self, HTTPStatus.NOT_FOUND, {"error": "Маршрут не найден."})

    def handle_metrics(self, parsed_path) -> None:
        if not INTERNAL_ANALYTICS_ENABLED:
            json_response(self, HTTPStatus.NOT_FOUND, {"error": "Встроенная аналитика отключена."})
            return
        if not METRICS_TOKEN:
            json_response(self, HTTPStatus.FORBIDDEN, {"error": "Сначала задайте METRICS_TOKEN в окружении."})
            return

        query = parse.parse_qs(parsed_path.query)
        token = str(query.get("token", [""])[0]).strip()
        if token != METRICS_TOKEN:
            json_response(self, HTTPStatus.FORBIDDEN, {"error": "Неверный token для метрик."})
            return

        json_response(self, HTTPStatus.OK, build_metrics_snapshot())

    def handle_track(self) -> None:
        try:
            payload = read_json(self)
            event = str(payload.get("event", "")).strip().lower()
            if not TRACK_EVENT_RE.fullmatch(event):
                raise ValueError("Некорректное имя события аналитики.")

            details = sanitize_event_details(payload.get("details"))
            track_event(event, {**request_context(self), "details": details})
            json_response(self, HTTPStatus.OK, {"ok": True})
        except ValueError as exc:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:
            json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"Внутренняя ошибка: {exc}"})

    def handle_chat(self) -> None:
        try:
            payload = read_json(self)
            message = str(payload.get("message", "")).strip()
            history = payload.get("history") or []

            if not message:
                raise ValueError("Введите сообщение для ассистента.")

            track_event(
                "assistant_prompt",
                {
                    **request_context(self),
                    "provider": AI_PROVIDER,
                    "message_length": len(message),
                },
            )

            reply = generate_ai_reply(history, message)

            telegram_sent = False
            try:
                telegram_sent = send_telegram_message(format_chat_alert(message, reply))
            except RuntimeError as exc:
                print(f"[telegram chat warning] {exc}", file=sys.stderr)

            track_event(
                "assistant_reply",
                {
                    **request_context(self),
                    "provider": AI_PROVIDER,
                    "telegram_sent": telegram_sent,
                    "reply_length": len(reply),
                },
            )

            json_response(self, HTTPStatus.OK, {"reply": reply, "telegram_sent": telegram_sent})
        except ValueError as exc:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except RuntimeError as exc:
            track_event("assistant_error", {**request_context(self), "provider": AI_PROVIDER, "error": clip_text(exc, 180)})
            json_response(self, HTTPStatus.BAD_GATEWAY, {"error": str(exc)})
        except Exception as exc:
            json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"Внутренняя ошибка: {exc}"})

    def handle_contact(self) -> None:
        try:
            fields, upload = read_contact_submission(self)
            name = str(fields.get("name", "")).strip()
            contact = str(fields.get("contact", "")).strip()
            task = str(fields.get("task", "")).strip()

            if not task:
                raise ValueError("Опишите задачу перед отправкой.")
            if not contact:
                raise ValueError("Укажите телефон или Telegram для обратной связи.")

            lead_id = uuid.uuid4().hex[:10].upper()
            upload_meta = save_uploaded_file(upload, lead_id) if upload else None

            telegram_sent = send_telegram_message(format_contact_alert(lead_id, name, contact, task, upload_meta))
            if not telegram_sent:
                raise RuntimeError("Не настроен LEADS_TELEGRAM_BOT_TOKEN или LEADS_TELEGRAM_CHAT_ID.")

            file_sent = False
            if upload:
                try:
                    file_sent = send_telegram_document(upload, lead_id)
                except RuntimeError as exc:
                    print(f"[telegram file warning] {exc}", file=sys.stderr)

            track_event(
                "lead_submitted",
                {
                    **request_context(self),
                    "lead_id": lead_id,
                    "source": "contact_form",
                    "has_file": bool(upload),
                    "telegram_sent": telegram_sent,
                    "file_sent": file_sent,
                },
            )

            json_response(
                self,
                HTTPStatus.OK,
                {
                    "message": "Заявка отправлена. Мы свяжемся с вами после первичной оценки.",
                    "lead_id": lead_id,
                    "telegram_sent": telegram_sent,
                    "file_uploaded": bool(upload),
                    "file_sent": file_sent,
                },
            )
        except ValueError as exc:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except RuntimeError as exc:
            track_event("lead_submit_failed", {**request_context(self), "error": clip_text(exc, 180)})
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
