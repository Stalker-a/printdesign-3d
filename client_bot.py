import json
import os
import time
from pathlib import Path
from urllib import error, request

from server import BASE_DIR, DATA_DIR, SITE_NAME, generate_ai_reply, load_env, send_telegram_message


load_env(BASE_DIR / ".env")


CLIENT_TELEGRAM_BOT_TOKEN = os.getenv("CLIENT_TELEGRAM_BOT_TOKEN", "").strip()
CLIENT_TELEGRAM_BOT_URL = os.getenv("CLIENT_TELEGRAM_BOT_URL", "https://t.me/your_client_bot").strip()
CLIENT_TELEGRAM_BOT_LABEL = os.getenv("CLIENT_TELEGRAM_BOT_LABEL", "@your_client_bot").strip()
CLIENT_BOT_HISTORY_LIMIT = int(os.getenv("CLIENT_BOT_HISTORY_LIMIT", "10"))
CLIENT_BOT_POLL_TIMEOUT = int(os.getenv("CLIENT_BOT_POLL_TIMEOUT", "25"))

SESSIONS_PATH = DATA_DIR / "client_bot_sessions.json"
STATE_PATH = DATA_DIR / "client_bot_state.json"
LEADS_PATH = DATA_DIR / "client_bot_leads.json"


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def read_json(path: Path, default):
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def telegram_api(method: str, payload: dict) -> dict:
    if not CLIENT_TELEGRAM_BOT_TOKEN:
        raise RuntimeError("Не задан CLIENT_TELEGRAM_BOT_TOKEN в .env")

    req = request.Request(
        f"https://api.telegram.org/bot{CLIENT_TELEGRAM_BOT_TOKEN}/{method}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Telegram API error: {details or exc.reason}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Telegram недоступен: {exc.reason}") from exc

    if not data.get("ok"):
        raise RuntimeError(f"Telegram error: {data}")

    return data


def send_chat_action(chat_id: int, action: str = "typing") -> None:
    try:
        telegram_api("sendChatAction", {"chat_id": chat_id, "action": action})
    except RuntimeError:
        pass


def send_message(chat_id: int, text: str) -> None:
    telegram_api(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        },
    )


def get_updates(offset: int | None) -> list[dict]:
    payload = {
        "timeout": CLIENT_BOT_POLL_TIMEOUT,
        "allowed_updates": ["message"],
    }
    if offset is not None:
        payload["offset"] = offset

    data = telegram_api("getUpdates", payload)
    return data.get("result", [])


def load_sessions() -> dict[str, list[dict]]:
    data = read_json(SESSIONS_PATH, {})
    return data if isinstance(data, dict) else {}


def save_sessions(sessions: dict[str, list[dict]]) -> None:
    write_json(SESSIONS_PATH, sessions)


def load_offset() -> int | None:
    state = read_json(STATE_PATH, {})
    if not isinstance(state, dict):
        return None
    value = state.get("last_update_id")
    return value if isinstance(value, int) else None


def save_offset(update_id: int) -> None:
    write_json(STATE_PATH, {"last_update_id": update_id})


def load_leads() -> dict[str, dict]:
    data = read_json(LEADS_PATH, {})
    return data if isinstance(data, dict) else {}


def save_leads(leads: dict[str, dict]) -> None:
    write_json(LEADS_PATH, leads)


def start_message(first_name: str) -> str:
    name = first_name.strip() or "друг"
    return (
        f"Здравствуйте, {name}. Я Telegram-бот проекта {SITE_NAME}.\n\n"
        "Можете написать, что нужно изготовить, отсканировать или восстановить. "
        "Я подскажу по 3D-печати, 3D-сканированию, материалам и подготовке модели.\n\n"
        "Команды:\n"
        "/start - приветствие\n"
        "/reset - сбросить историю диалога\n"
        "/lead - отправить заявку через этого бота\n\n"
        f"Если удобнее, сайт и форма заявок доступны здесь: {CLIENT_TELEGRAM_BOT_URL}"
    )


def reset_message() -> str:
    return (
        "История диалога очищена. Можете задать новый вопрос по 3D-печати, "
        "3D-сканированию или изготовлению детали."
    )


def lead_intro_message() -> str:
    return (
        "Давайте оформим заявку. Сначала отправьте контакт для обратной связи: "
        "телефон, @username или удобный способ связи."
    )


def lead_task_message() -> str:
    return (
        "Теперь коротко опишите задачу: что нужно изготовить, отсканировать "
        "или восстановить."
    )


def lead_success_message() -> str:
    return (
        "Заявка отправлена. Мы получили ваш контакт и описание задачи. "
        "Если нужно, можете продолжить диалог здесь."
    )


def lead_cancel_message() -> str:
    return "Черновик заявки очищен."


def unsupported_message() -> str:
    return (
        "Пока я умею обрабатывать только текстовые сообщения. "
        "Опишите задачу словами, а файл или фото удобнее отправить через сайт."
    )


def html_escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def format_client_lead_alert(
    first_name: str,
    username: str,
    user_id: int,
    contact: str,
    task: str,
) -> str:
    username_line = f"@{username}" if username else "не указан"
    return (
        "<b>Новая заявка из клиентского Telegram-бота</b>\n"
        f"<b>Сайт:</b> {html_escape(SITE_NAME)}\n\n"
        f"<b>Имя в Telegram:</b> {html_escape(first_name or 'Не указано')}\n"
        f"<b>Username:</b> {html_escape(username_line)}\n"
        f"<b>Telegram user id:</b> {user_id}\n"
        f"<b>Контакт:</b> {html_escape(contact)}\n\n"
        f"<b>Задача:</b>\n{html_escape(task)}"
    )


def normalize_reply(text: str) -> str:
    cleaned = str(text).strip()
    return cleaned or "Сейчас не удалось сформировать ответ. Попробуйте переформулировать вопрос."


def trim_history(history: list[dict]) -> list[dict]:
    cleaned = []
    for item in history[-CLIENT_BOT_HISTORY_LIMIT * 2 :]:
        role = item.get("role")
        content = str(item.get("content", "")).strip()
        if role in {"user", "assistant"} and content:
            cleaned.append({"role": role, "content": content})
    return cleaned[-CLIENT_BOT_HISTORY_LIMIT * 2 :]


def handle_lead_flow(chat_id: int, text: str, leads: dict[str, dict], message: dict) -> bool:
    session_key = str(chat_id)

    if text == "/lead_cancel":
        leads.pop(session_key, None)
        save_leads(leads)
        send_message(chat_id, lead_cancel_message())
        return True

    current = leads.get(session_key)
    if not current:
        return False

    if current.get("step") == "contact":
        current["contact"] = text
        current["step"] = "task"
        leads[session_key] = current
        save_leads(leads)
        send_message(chat_id, lead_task_message())
        return True

    if current.get("step") == "task":
        from_user = message.get("from") or {}
        first_name = str(from_user.get("first_name", "")).strip()
        username = str(from_user.get("username", "")).strip()
        user_id = int(from_user.get("id") or chat_id)

        alert = format_client_lead_alert(
            first_name=first_name,
            username=username,
            user_id=user_id,
            contact=str(current.get("contact", "")).strip(),
            task=text,
        )
        telegram_sent = send_telegram_message(alert)
        if not telegram_sent:
            raise RuntimeError("Не настроен LEADS_TELEGRAM_BOT_TOKEN или LEADS_TELEGRAM_CHAT_ID.")

        leads.pop(session_key, None)
        save_leads(leads)
        send_message(chat_id, lead_success_message())
        return True

    return False


def handle_text_message(chat_id: int, text: str, sessions: dict[str, list[dict]]) -> None:
    session_key = str(chat_id)
    history = trim_history(sessions.get(session_key, []))

    if text == "/reset":
        sessions[session_key] = []
        save_sessions(sessions)
        send_message(chat_id, reset_message())
        return

    send_chat_action(chat_id, "typing")
    reply = normalize_reply(generate_ai_reply(history, text))

    history.append({"role": "user", "content": text})
    history.append({"role": "assistant", "content": reply})
    sessions[session_key] = trim_history(history)
    save_sessions(sessions)
    send_message(chat_id, reply)


def process_update(update: dict, sessions: dict[str, list[dict]], leads: dict[str, dict]) -> None:
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")

    if not chat_id:
        return

    text = str(message.get("text", "")).strip()
    first_name = str((message.get("from") or {}).get("first_name", "")).strip()

    if text == "/start":
        send_message(chat_id, start_message(first_name))
        return

    if text == "/lead":
        leads[str(chat_id)] = {"step": "contact", "contact": ""}
        save_leads(leads)
        send_message(chat_id, lead_intro_message())
        return

    if not text:
        send_message(chat_id, unsupported_message())
        return

    try:
        if handle_lead_flow(chat_id, text, leads, message):
            return
        handle_text_message(chat_id, text, sessions)
    except Exception as exc:
        send_message(
            chat_id,
            (
                "Сейчас не удалось обработать сообщение. "
                f"Техническая причина: {str(exc).strip() or 'неизвестная ошибка'}"
            ),
        )


def main() -> None:
    if not CLIENT_TELEGRAM_BOT_TOKEN:
        raise SystemExit("Укажите CLIENT_TELEGRAM_BOT_TOKEN в .env")

    print(f"Client bot started for {CLIENT_TELEGRAM_BOT_LABEL or SITE_NAME}")
    sessions = load_sessions()
    leads = load_leads()
    offset = load_offset()

    while True:
        try:
            updates = get_updates(None if offset is None else offset + 1)
            for update in updates:
                update_id = update.get("update_id")
                if not isinstance(update_id, int):
                    continue

                process_update(update, sessions, leads)
                offset = update_id
                save_offset(update_id)
        except KeyboardInterrupt:
            print("\nClient bot stopped.")
            break
        except Exception as exc:
            print(f"[client bot warning] {exc}")
            time.sleep(3)


if __name__ == "__main__":
    main()
