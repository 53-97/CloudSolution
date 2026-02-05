import os
import json
import urllib.parse
import urllib.request
import logging
import traceback
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key

# ---------------- Config ----------------

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
    Write structured JSON logs to CloudWatch.
    Every log entry includes timestamp + level, plus additional consistent fields.
    """
    payload = {
        "timestamp": now_iso(),
        "level": level,
        **fields,
    }
    msg = json.dumps(payload, ensure_ascii=False)

    if level == "ERROR":
        logger.error(msg)
    elif level == "WARNING":
        logger.warning(msg)
    else:
        logger.info(msg)


def parse_update(update: dict):
    """
    Extract common identifiers from Telegram update.
    Supports message updates and callback_query updates.
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


def send_message(chat_id: int, text: str, request_id: str | None = None, user_id: int | None = None,
                 message_id: int | None = None, command: str | None = None):
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


def tg_download_file(file_path: str) -> bytes:
    url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
    with urllib.request.urlopen(url) as r:
        return r.read()


# ---------------- Bot features ----------------

def handle_text(text: str, user_id: int, request_id: str | None = None, message_id: int | None = None) -> str:
    text = (text or "").strip()
    command = detect_command(text) or "message"

    # Intentional error trigger (Task 9 verification)
    if command == "/error":
        raise RuntimeError("Intentional error for Task 9 CloudWatch alarm verification")

    if text.startswith("/hello"):
        return "Hello! 👋 Telegram bot is live."

    if text.startswith("/help"):
        return (
            "Available commands:\n"
            "/hello – greeting\n"
            "/help – show help\n"
            "/echo <text> – echo back\n"
            "/save <text> – save a note\n"
            "/get – list your notes\n"
            "/files – list your uploaded files\n"
            "/error – trigger an intentional error (Task 9)\n"
            "Send any photo/document to upload it to S3."
        )

    if text.startswith("/echo"):
        parts = text.split(" ", 1)
        return parts[1] if len(parts) > 1 else "Usage: /echo <text>"

    if text.startswith("/save"):
        parts = text.split(" ", 1)
        if len(parts) < 2:
            return "Usage: /save <text>"
        note = parts[1]
        ts = datetime.utcnow().isoformat()
        table.put_item(Item={
            "user_id": str(user_id),
            "item_id": ts,
            "text": note,
            "created_at": ts
        })
        log_event(
            "INFO",
            request_id=request_id,
            message_id=message_id,
            user_id=user_id,
            command=command,
            action="ddb_put_item",
            outcome="success",
        )
        return "✅ Saved your note!"

    if text.startswith("/get"):
        resp = table.query(KeyConditionExpression=Key("user_id").eq(str(user_id)))
        items = resp.get("Items", [])
        if not items:
            return "You have no saved notes. Use /save <text>."
        items = sorted(items, key=lambda x: x.get("created_at", ""))
        return "Your notes:\n" + "\n".join(f"- {i.get('text','')}" for i in items)

    if text.startswith("/files"):
        prefix = f"{user_id}/"
        resp = s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix)
        contents = resp.get("Contents", [])
        if not contents:
            return "You have no uploaded files yet."
        names = [obj["Key"].split("/", 1)[1] for obj in contents]
        return "Your files:\n" + "\n".join(f"- {n}" for n in names)

    return "Unknown command. Try /help"


def handle_file_upload(file_id: str, filename: str, chat_id: int, user_id: int,
                       request_id: str | None = None, message_id: int | None = None):
    """
    Downloads file from Telegram and stores it in S3 under <user_id>/<file_id>_<filename>
    """
    try:
        # 1) get Telegram file path
        info = tg_request("getFile", {"file_id": file_id})
        if not info.get("ok"):
            send_message(chat_id, "❌ Could not fetch file info from Telegram.", request_id, user_id, message_id, "upload")
            return

        file_path = info["result"]["file_path"]

        # 2) download bytes
        data = tg_download_file(file_path)

        # 3) store in S3 using user folder structure
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

        send_message(chat_id, f"📁 Saved to S3:\n{key}", request_id, user_id, message_id, "upload")

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
    event["body"] is the Telegram update JSON as a string.
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

        msg = update.get("message")
        if not msg:
            # no message: could be other event types
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
        reply = handle_text(text, user_id, request_id, message_id)
        send_message(chat_id, reply, request_id, user_id, message_id, detect_command(text) or "message")

        log_event(
            "INFO",
            request_id=request_id,
            message_id=message_id,
            user_id=user_id,
            command=detect_command(text) or "message",
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
        # Telegram expects 200 quickly; still return 200 to avoid retry storms
        return {"statusCode": 200, "body": "error_logged"}
