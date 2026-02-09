import os
import json
import urllib.parse
import urllib.request
import logging
import traceback
import random
import html
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key

# ---------------- Config ----------------
# NOTE: Never hardcode tokens. Keep them in Lambda env vars via Terraform.
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TG_API = f"https://api.telegram.org/bot{TOKEN}"

TABLE_NAME = os.environ["USER_DATA_TABLE_NAME"]
BUCKET = os.environ["S3_BUCKET"]

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)
s3 = boto3.client("s3")

# ---------------- Structured logging (Task 9) ----------------
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_event(level: str, **fields):
    """
    Structured JSON logs to CloudWatch.
    Consistent fields: level, timestamp, request_id/message_id, user_id, command/action, outcome, error details.
    """
    payload = {"timestamp": now_iso(), "level": level, **fields}
    msg = json.dumps(payload, ensure_ascii=False)

    if level == "ERROR":
        logger.error(msg)
    elif level == "WARNING":
        logger.warning(msg)
    else:
        logger.info(msg)


def parse_update(update: dict):
    """
    Extract identifiers from Telegram update.
    Supports message + edited_message + callback_query.
    """
    message = update.get("message") or update.get("edited_message")
    callback = update.get("callback_query")

    user_id = None
    message_id = None
    text = ""

    if message:
        user_id = (message.get("from") or {}).get("id")
        message_id = message.get("message_id") or update.get("update_id")
        text = message.get("text") or ""
    elif callback:
        user = callback.get("from") or {}
        user_id = user.get("id")
        msg = callback.get("message") or {}
        message_id = msg.get("message_id") or update.get("update_id")
        text = callback.get("data") or ""

    return user_id, message_id, text


def detect_command(text: str):
    text = (text or "").strip()
    if text.startswith("/"):
        return text.split(" ", 1)[0].lower()
    return None


# ---------------- HTTP helper ----------------
def http_get_json(url: str, timeout: int = 8) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "cloudsolution-telegram-bot/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def http_get_text(url: str, timeout: int = 10) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "cloudsolution-telegram-bot/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")


# ---------------- Telegram helpers ----------------
def tg_request(method: str, params: dict | None = None) -> dict:
    if params is None:
        params = {}
    url = TG_API + "/" + method + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read())


def tg_post(method: str, data: dict) -> dict:
    url = TG_API + "/" + method
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=encoded)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def send_message(
    chat_id: int,
    text: str,
    request_id: str | None = None,
    user_id: int | None = None,
    message_id: int | None = None,
    command: str | None = None,
):
    try:
        tg_post("sendMessage", {"chat_id": chat_id, "text": text})
        log_event(
            "INFO",
            request_id=request_id,
            message_id=message_id,
            user_id=user_id,
            command=command,
            action="send_message",
            outcome="success",
        )
    except Exception as e:
        log_event(
            "ERROR",
            request_id=request_id,
            message_id=message_id,
            user_id=user_id,
            command=command,
            action="send_message",
            outcome="error",
            error_type=type(e).__name__,
            error_message=str(e),
            stack_trace=traceback.format_exc(),
        )


def send_message_with_keyboard(
    chat_id: int,
    text: str,
    reply_markup: dict,
    request_id: str | None = None,
    user_id: int | None = None,
    message_id: int | None = None,
    command: str | None = None,
):
    try:
        tg_post(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text,
                "reply_markup": json.dumps(reply_markup, ensure_ascii=False),
            },
        )
        log_event(
            "INFO",
            request_id=request_id,
            message_id=message_id,
            user_id=user_id,
            command=command,
            action="send_message_keyboard",
            outcome="success",
        )
    except Exception as e:
        log_event(
            "ERROR",
            request_id=request_id,
            message_id=message_id,
            user_id=user_id,
            command=command,
            action="send_message_keyboard",
            outcome="error",
            error_type=type(e).__name__,
            error_message=str(e),
            stack_trace=traceback.format_exc(),
        )


def answer_callback(callback_query_id: str, text: str, show_alert: bool = False):
    # Toast for inline button clicks
    try:
        tg_post(
            "answerCallbackQuery",
            {
                "callback_query_id": callback_query_id,
                "text": text,
                "show_alert": "true" if show_alert else "false",
            },
        )
    except Exception:
        pass


def tg_download_file(file_path: str) -> bytes:
    url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
    with urllib.request.urlopen(url) as r:
        return r.read()


# ---------------- Weather (Open-Meteo, no key) ----------------
def weather_by_city(city: str) -> str:
    city = (city or "").strip()
    if not city:
        return "🌦 Usage: /weather <city>\nExample: /weather Leipzig"

    geo_url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode(
        {"name": city, "count": 1, "language": "en", "format": "json"}
    )
    geo = http_get_json(geo_url)
    results = geo.get("results") or []
    if not results:
        return f"❌ City not found: {city}"

    place = results[0]
    lat, lon = place["latitude"], place["longitude"]
    name = place.get("name", city)
    country = place.get("country", "")

    forecast_url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(
        {
            "latitude": lat,
            "longitude": lon,
            "current_weather": "true",
            "daily": "temperature_2m_max,temperature_2m_min",
            "timezone": "auto",
        }
    )
    fc = http_get_json(forecast_url)

    cur = fc.get("current_weather") or {}
    daily = fc.get("daily") or {}
    t = cur.get("temperature")
    wind = cur.get("windspeed")
    tmax = (daily.get("temperature_2m_max") or [None])[0]
    tmin = (daily.get("temperature_2m_min") or [None])[0]

    loc = f"{name}{', ' + country if country else ''}"
    return f"🌦 Weather for {loc}\nNow: {t}°C, wind {wind} km/h\nToday: min {tmin}°C / max {tmax}°C"


# ---------------- Trivia (Open Trivia DB, no key) ----------------
def trivia_fetch_question() -> dict:
    data = http_get_json("https://opentdb.com/api.php?amount=1&type=multiple")
    results = data.get("results") or []
    if not results:
        raise RuntimeError("Trivia API returned no questions")

    q = results[0]
    question = html.unescape(q.get("question", ""))
    correct = html.unescape(q.get("correct_answer", ""))
    incorrect = [html.unescape(x) for x in (q.get("incorrect_answers") or [])]

    options = incorrect + [correct]
    random.shuffle(options)
    correct_index = options.index(correct)
    return {"question": question, "options": options, "correct_index": correct_index}


def trivia_save_active(user_id: int, trivia: dict):
    table.put_item(
        Item={
            "user_id": str(user_id),
            "item_id": "trivia#active",
            "question": trivia["question"],
            "options": trivia["options"],
            "correct_index": trivia["correct_index"],
            "created_at": datetime.utcnow().isoformat(),
        }
    )


def trivia_get_active(user_id: int) -> dict | None:
    resp = table.get_item(Key={"user_id": str(user_id), "item_id": "trivia#active"})
    return resp.get("Item")


def trivia_clear_active(user_id: int):
    # Cleaner UX: after answering, clear the active trivia so buttons can't be reused forever.
    table.delete_item(Key={"user_id": str(user_id), "item_id": "trivia#active"})


def trivia_build_keyboard(options: list[str]) -> dict:
    keyboard = []
    for i, opt in enumerate(options):
        keyboard.append([{"text": opt, "callback_data": f"trivia:{i}"}])
    return {"inline_keyboard": keyboard}


# ---------------- News (English-only, no key) ----------------
def news_search(topic: str, max_records: int = 5) -> str:
    """
    English-only news results using Google News RSS.
    No API key required.
    """
    topic = (topic or "").strip() or "technology"

    rss_url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {
            "q": topic,
            "hl": "en-US",
            "gl": "US",
            "ceid": "US:en",
        }
    )

    xml_data = http_get_text(rss_url, timeout=10)

    try:
        root = ET.fromstring(xml_data)
    except Exception:
        return "📰 News service temporarily unavailable. Try again in a minute."

    items = root.findall(".//channel/item")
    if not items:
        return f"📰 No English news found for: {topic}"

    lines = [f"📰 Top English news for: {topic}"]
    for i, item in enumerate(items[:max_records], 1):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        source = ""
        src_el = item.find("source")
        if src_el is not None and src_el.text:
            source = src_el.text.strip()

        if len(title) > 130:
            title = title[:127] + "..."

        meta = f" ({source})" if source else ""
        lines.append(f"{i}. {title}{meta}\n{link}")

    lines.append("\nTip: /news germany  •  /news ai  •  /news EU trade deals")
    return "\n\n".join(lines)


# ---------------- Card game: High Card (Deck of Cards API, no key) ----------------
CARD_VALUE = {
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "7": 7,
    "8": 8,
    "9": 9,
    "10": 10,
    "JACK": 11,
    "QUEEN": 12,
    "KING": 13,
    "ACE": 14,
}


def card_state_key(user_id: int) -> dict:
    return {"user_id": str(user_id), "item_id": "card#state"}


def card_get_state(user_id: int) -> dict | None:
    resp = table.get_item(Key=card_state_key(user_id))
    return resp.get("Item")


def card_set_state(user_id: int, deck_id: str):
    table.put_item(
        Item={"user_id": str(user_id), "item_id": "card#state", "deck_id": deck_id, "created_at": datetime.utcnow().isoformat()}
    )


def card_delete_state(user_id: int):
    table.delete_item(Key=card_state_key(user_id))


def deck_new() -> str:
    data = http_get_json("https://deckofcardsapi.com/api/deck/new/shuffle/?deck_count=1")
    if not data.get("success"):
        raise RuntimeError("Deck API failed to create new deck")
    return data["deck_id"]


def deck_draw(deck_id: str, count: int = 2) -> dict:
    return http_get_json(f"https://deckofcardsapi.com/api/deck/{deck_id}/draw/?count={count}")


def format_card(c: dict) -> str:
    return f"{c.get('value')} of {c.get('suit')}"


def high_card_result(c1: dict, c2: dict) -> str:
    v1 = CARD_VALUE.get(c1.get("value"), 0)
    v2 = CARD_VALUE.get(c2.get("value"), 0)
    if v1 > v2:
        return "✅ You win!"
    if v2 > v1:
        return "❌ Bot wins!"
    return "🤝 It's a tie!"


def card_help_text(state: dict | None) -> str:
    status = "No active deck. Start with /card new" if not state else "Deck ready ✅"
    return (
        "🃏 High Card\n"
        f"Status: {status}\n\n"
        "Commands:\n"
        "/card new   – create/reset deck\n"
        "/card draw  – draw (you vs bot)\n"
        "/card reset – forget deck\n"
    )


def card_draw_flow(user_id: int) -> str:
    # Cleaner UX: auto-create deck if missing; auto-reset if draw fails.
    state = card_get_state(user_id)
    deck_id = state.get("deck_id") if state else None

    if not deck_id:
        deck_id = deck_new()
        card_set_state(user_id, deck_id)

    draw = deck_draw(deck_id, 2)
    if not draw.get("success"):
        card_delete_state(user_id)
        return "❌ Deck problem. I reset it — run /card new and try again."

    cards = draw.get("cards") or []
    if len(cards) < 2:
        card_delete_state(user_id)
        return "❌ Not enough cards. I reset it — run /card new."

    remaining = draw.get("remaining")
    you, bot = cards[0], cards[1]
    verdict = high_card_result(you, bot)

    return (
        "🃏 High Card!\n"
        f"You: {format_card(you)}\n"
        f"Bot: {format_card(bot)}\n"
        f"{verdict}\n"
        f"Cards remaining: {remaining}"
    )


# ---------------- S3 download (presigned URL) ----------------
def s3_presigned_download_url(user_id: int, filename: str, expires_seconds: int = 600) -> str:
    """
    Generate a temporary download URL for an object stored as:
      s3://<bucket>/<user_id>/<filename>

    filename should match the exact string you see in /files output
    (e.g., "<file_id>_<original_name>").
    """
    filename = (filename or "").strip()
    if not filename:
        return "⬇️ Usage: /download <filename>\nExample: /download 12345_myfile.pdf\nTip: use /files to copy the filename."

    key = f"{user_id}/{filename}"

    try:
        url = s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": BUCKET, "Key": key},
            ExpiresIn=expires_seconds,
        )
        log_event("INFO", user_id=user_id, command="/download", action="s3_presign_get_object", outcome="success", s3_key=key)
        return (
            "⬇️ Download link (valid for 10 minutes):\n"
            f"{url}\n\n"
            "Tip: Use /files to see filenames."
        )
    except Exception as e:
        log_event(
            "ERROR",
            user_id=user_id,
            command="/download",
            action="s3_presign_get_object",
            outcome="error",
            error_type=type(e).__name__,
            error_message=str(e),
            stack_trace=traceback.format_exc(),
            s3_key=key,
        )
        return "❌ Could not generate download link. Check the filename (use /files) and try again."


# ---------------- Bot features ----------------
def help_text() -> str:
    # Cleaner UX: grouped, short, easy to scan
    return (
        "🤖 Commands\n"
        "Basics:\n"
        "• /hello\n"
        "• /help\n"
        "• /echo <text>\n\n"
        "Notes:\n"
        "• /save <text>\n"
        "• /get\n\n"
        "Files:\n"
        "• Send a photo/document to upload to S3\n"
        "• /files\n"
        "• /download <filename>\n\n"
        "APIs (no key):\n"
        "• /weather <city>\n"
        "• /news <topic>  (English)\n"
        "• /trivia\n\n"
        "Games:\n"
        "• /card  (High Card)\n\n"
        "Monitoring:\n"
        "• /error (intentional error test)\n"
    )


def handle_text(text: str, user_id: int, request_id: str | None = None, message_id: int | None = None) -> str:
    text = (text or "").strip()
    command = detect_command(text) or "message"

    if command == "/error":
        raise RuntimeError("Intentional error for CloudWatch alarm verification")

    if command in ("/help",):
        return help_text()

    if command in ("/start",):
        return "Welcome! 👋 Type /help to see what I can do."

    # ✅ (1) Friendlier hello
    if command == "/hello":
        return (
            "Hey! 👋😊 I’m your Cloud Solutions bot running serverless on AWS.\n\n"
            "Try these:\n"
            "• /weather Leipzig\n"
            "• /news EU trade deals\n"
            "• /trivia\n"
            "• /card\n\n"
            "Type /help anytime to see all commands."
        )

    if command == "/echo":
        parts = text.split(" ", 1)
        return parts[1] if len(parts) > 1 else "Usage: /echo <text>"

    if command == "/save":
        parts = text.split(" ", 1)
        if len(parts) < 2:
            return "Usage: /save <text>"
        note = parts[1]
        ts = datetime.utcnow().isoformat()
        table.put_item(Item={"user_id": str(user_id), "item_id": ts, "text": note, "created_at": ts})
        log_event(
            "INFO",
            request_id=request_id,
            message_id=message_id,
            user_id=user_id,
            command=command,
            action="ddb_put_item",
            outcome="success",
        )
        return "✅ Saved!"

    if command == "/get":
        resp = table.query(KeyConditionExpression=Key("user_id").eq(str(user_id)))
        items = resp.get("Items", [])
        # Hide internal state items (card/trivia)
        items = [i for i in items if not str(i.get("item_id", "")).startswith(("card#", "trivia#"))]
        if not items:
            return "You have no saved notes. Use /save <text>."
        items = sorted(items, key=lambda x: x.get("created_at", ""))
        lines = ["📝 Your notes:"]
        for i in items[-10:]:
            lines.append(f"- {i.get('text', '')}")
        return "\n".join(lines)

    if command == "/files":
        prefix = f"{user_id}/"
        resp = s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix)
        contents = resp.get("Contents", [])
        if not contents:
            return "You have no uploaded files yet."
        names = [obj["Key"].split("/", 1)[1] for obj in contents]
        names = names[:15]
        return (
            "📁 Your files:\n" + "\n".join(f"- {n}" for n in names)
            + "\n\n⬇️ Download: /download <filename>"
        )

    # ✅ (3) Download command
    if command == "/download":
        parts = text.split(" ", 1)
        filename = parts[1] if len(parts) > 1 else ""
        return s3_presigned_download_url(user_id, filename)

    if command == "/weather":
        parts = text.split(" ", 1)
        city = parts[1] if len(parts) > 1 else ""
        log_event(
            "INFO",
            request_id=request_id,
            message_id=message_id,
            user_id=user_id,
            command="/weather",
            action="weather_fetch",
            outcome="start",
            city=city or "",
        )
        return weather_by_city(city)

    # ✅ (2) English-only news
    if command == "/news":
        parts = text.split(" ", 1)
        topic = parts[1] if len(parts) > 1 else ""
        log_event(
            "INFO",
            request_id=request_id,
            message_id=message_id,
            user_id=user_id,
            command="/news",
            action="news_fetch",
            outcome="start",
            topic=topic or "technology",
        )
        return news_search(topic)

    if command == "/trivia":
        # handled in lambda_handler to send inline keyboard
        return "__TRIVIA__"

    if command == "/card":
        parts = text.split(" ", 2)
        sub = parts[1].lower() if len(parts) > 1 else "help"

        state = card_get_state(user_id)

        if sub in ("help", ""):
            return card_help_text(state)

        if sub == "new":
            deck_id = deck_new()
            card_set_state(user_id, deck_id)
            log_event(
                "INFO",
                request_id=request_id,
                message_id=message_id,
                user_id=user_id,
                command="/card",
                action="card_new",
                outcome="success",
                deck_id=deck_id,
            )
            return "🃏 New deck created! Now run /card draw"

        if sub == "reset":
            card_delete_state(user_id)
            log_event(
                "INFO",
                request_id=request_id,
                message_id=message_id,
                user_id=user_id,
                command="/card",
                action="card_reset",
                outcome="success",
            )
            return "♻️ Reset done. Run /card new"

        if sub == "draw":
            result = card_draw_flow(user_id)
            log_event(
                "INFO",
                request_id=request_id,
                message_id=message_id,
                user_id=user_id,
                command="/card",
                action="card_draw",
                outcome="success",
            )
            return result

        return card_help_text(state)

    return "I didn’t understand that. Type /help."


def handle_file_upload(
    file_id: str,
    filename: str,
    chat_id: int,
    user_id: int,
    request_id: str | None = None,
    message_id: int | None = None,
):
    """
    Download file from Telegram and store in S3 under <user_id>/<file_id>_<filename>
    """
    try:
        info = tg_request("getFile", {"file_id": file_id})
        if not info.get("ok"):
            send_message(chat_id, "❌ Could not fetch file info from Telegram.", request_id, user_id, message_id, "upload")
            return

        file_path = info["result"]["file_path"]
        data = tg_download_file(file_path)

        key = f"{user_id}/{file_id}_{filename}"
        s3.put_object(Bucket=BUCKET, Key=key, Body=data)

        log_event(
            "INFO",
            request_id=request_id,
            message_id=message_id,
            user_id=user_id,
            command="upload",
            action="s3_put_object",
            outcome="success",
            s3_key=key,
        )

        send_message(chat_id, f"📁 Uploaded!\n{key.split('/', 1)[1]}", request_id, user_id, message_id, "upload")

    except Exception as e:
        log_event(
            "ERROR",
            request_id=request_id,
            message_id=message_id,
            user_id=user_id,
            command="upload",
            action="file_upload",
            outcome="error",
            error_type=type(e).__name__,
            error_message=str(e),
            stack_trace=traceback.format_exc(),
        )
        send_message(chat_id, "❌ Upload failed. Please try again.", request_id, user_id, message_id, "upload")


# ---------------- Lambda handler (Webhook) ----------------
def lambda_handler(event, context):
    """
    Telegram -> API Gateway (HTTP API) -> Lambda
    event["body"] is Telegram update JSON string.
    """
    request_id = getattr(context, "aws_request_id", None)

    user_id = None
    message_id = None
    command = None

    try:
        body_raw = event.get("body", "{}")

        if event.get("isBase64Encoded"):
            import base64
            body_raw = base64.b64decode(body_raw).decode("utf-8")

        update = json.loads(body_raw)
        user_id, message_id, text = parse_update(update)
        command = detect_command(text) or "message"

        log_event(
            "INFO",
            request_id=request_id,
            message_id=message_id,
            user_id=user_id,
            command=command,
            action="incoming_update",
            outcome="received",
        )

        # -------- callback_query: Trivia answers --------
        if "callback_query" in update:
            cq = update["callback_query"]
            callback_id = cq.get("id")
            user_id = (cq.get("from") or {}).get("id")
            data = cq.get("data") or ""
            msg = cq.get("message") or {}
            chat_id = (msg.get("chat") or {}).get("id")
            message_id = msg.get("message_id")

            if data.startswith("trivia:"):
                try:
                    picked = int(data.split(":", 1)[1])
                except Exception:
                    answer_callback(callback_id, "Invalid answer.", show_alert=False)
                    return {"statusCode": 200, "body": "ok"}

                active = trivia_get_active(user_id)
                if not active:
                    answer_callback(callback_id, "No active trivia. Send /trivia", show_alert=False)
                    return {"statusCode": 200, "body": "ok"}

                correct = int(active.get("correct_index", -1))
                options = active.get("options") or []
                correct_text = options[correct] if 0 <= correct < len(options) else "(unknown)"

                trivia_clear_active(user_id)

                if picked == correct:
                    answer_callback(callback_id, "✅ Correct!", show_alert=False)
                    if chat_id:
                        send_message(chat_id, "✅ Correct! 🎉 Send /trivia for another.", request_id, user_id, message_id, "/trivia")
                    log_event(
                        "INFO",
                        request_id=request_id,
                        message_id=message_id,
                        user_id=user_id,
                        command="/trivia",
                        action="trivia_answer",
                        outcome="success",
                    )
                else:
                    answer_callback(callback_id, "❌ Wrong!", show_alert=False)
                    if chat_id:
                        send_message(chat_id, f"❌ Wrong. Correct: {correct_text}\nSend /trivia again!", request_id, user_id, message_id, "/trivia")
                    log_event(
                        "INFO",
                        request_id=request_id,
                        message_id=message_id,
                        user_id=user_id,
                        command="/trivia",
                        action="trivia_answer",
                        outcome="wrong",
                    )

                return {"statusCode": 200, "body": "ok"}

            return {"statusCode": 200, "body": "ok"}

        # -------- message updates --------
        msg = update.get("message")
        if not msg:
            log_event(
                "INFO",
                request_id=request_id,
                message_id=message_id,
                user_id=user_id,
                command=command,
                action="ignore_update",
                outcome="success",
            )
            return {"statusCode": 200, "body": "ok"}

        chat_id = msg["chat"]["id"]
        user_id = msg.get("from", {}).get("id", chat_id)
        message_id = msg.get("message_id") or message_id

        # Photo upload
        if "photo" in msg:
            photo = msg["photo"][-1]
            handle_file_upload(photo["file_id"], "photo.jpg", chat_id, user_id, request_id, message_id)
            return {"statusCode": 200, "body": "ok"}

        # Document upload
        if "document" in msg:
            doc = msg["document"]
            handle_file_upload(doc["file_id"], doc.get("file_name", "file.bin"), chat_id, user_id, request_id, message_id)
            return {"statusCode": 200, "body": "ok"}

        # Text commands
        text = msg.get("text", "")
        cmd = detect_command(text) or "message"

        # /trivia needs keyboard
        if cmd == "/trivia":
            trivia = trivia_fetch_question()
            trivia_save_active(user_id, trivia)

            log_event(
                "INFO",
                request_id=request_id,
                message_id=message_id,
                user_id=user_id,
                command="/trivia",
                action="trivia_question",
                outcome="success",
            )

            question_text = "🧠 Trivia:\n" + trivia["question"]
            kb = trivia_build_keyboard(trivia["options"])
            send_message_with_keyboard(chat_id, question_text, kb, request_id, user_id, message_id, "/trivia")
            return {"statusCode": 200, "body": "ok"}

        reply = handle_text(text, user_id, request_id, message_id)
        send_message(chat_id, reply, request_id, user_id, message_id, cmd)

        log_event(
            "INFO",
            request_id=request_id,
            message_id=message_id,
            user_id=user_id,
            command=cmd,
            action="handle_update",
            outcome="success",
        )

        return {"statusCode": 200, "body": "ok"}

    except Exception as e:
        log_event(
            "ERROR",
            request_id=request_id,
            message_id=message_id,
            user_id=user_id,
            command=command,
            action="handle_update",
            outcome="error",
            error_type=type(e).__name__,
            error_message=str(e),
            stack_trace=traceback.format_exc(),
        )
        # Telegram expects 200 quickly to avoid retries
        return {"statusCode": 200, "body": "error_logged"}
