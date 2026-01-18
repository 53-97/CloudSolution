import os
import json
import urllib.parse
import urllib.request
from datetime import datetime

import boto3
from boto3.dynamodb.conditions import Key

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TG_API = f"https://api.telegram.org/bot{TOKEN}"

TABLE_NAME = os.environ["USER_DATA_TABLE_NAME"]
BUCKET = os.environ["S3_BUCKET"]

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)

s3 = boto3.client("s3")


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

def send_message(chat_id: int, text: str):
    try:
        tg_post("sendMessage", {"chat_id": chat_id, "text": text})
    except Exception as e:
        print("send_message error:", e)

def tg_download_file(file_path: str) -> bytes:
    url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
    with urllib.request.urlopen(url) as r:
        return r.read()


# ---------------- Bot features ----------------

def handle_text(text: str, user_id: int) -> str:
    text = (text or "").strip()

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


def handle_file_upload(file_id: str, filename: str, chat_id: int, user_id: int):
    # 1) get Telegram file path
    info = tg_request("getFile", {"file_id": file_id})
    if not info.get("ok"):
        send_message(chat_id, "❌ Could not fetch file info from Telegram.")
        return

    file_path = info["result"]["file_path"]

    # 2) download bytes
    data = tg_download_file(file_path)

    # 3) store in S3 using user folder structure
    key = f"{user_id}/{file_id}_{filename}"

    s3.put_object(Bucket=BUCKET, Key=key, Body=data)
    send_message(chat_id, f"📁 Saved to S3:\n{key}")


# ---------------- Lambda handler (Webhook) ----------------

def lambda_handler(event, context):
    """
    Telegram -> API Gateway (HTTP API) -> Lambda
    event["body"] is the Telegram update JSON as a string.
    """
    try:
        body_raw = event.get("body", "{}")
        if event.get("isBase64Encoded"):
            # Usually false for Telegram, but handle anyway
            import base64
            body_raw = base64.b64decode(body_raw).decode("utf-8")

        update = json.loads(body_raw)
        msg = update.get("message")
        if not msg:
            return {"statusCode": 200, "body": "ok"}

        chat_id = msg["chat"]["id"]
        user_id = msg.get("from", {}).get("id", chat_id)

        # Photo upload
        if "photo" in msg:
            photo = msg["photo"][-1]
            handle_file_upload(photo["file_id"], "photo.jpg", chat_id, user_id)
            return {"statusCode": 200, "body": "ok"}

        # Document upload
        if "document" in msg:
            doc = msg["document"]
            handle_file_upload(doc["file_id"], doc.get("file_name", "file.bin"), chat_id, user_id)
            return {"statusCode": 200, "body": "ok"}

        # Text commands
        text = msg.get("text", "")
        reply = handle_text(text, user_id)
        send_message(chat_id, reply)

        return {"statusCode": 200, "body": "ok"}

    except Exception as e:
        print("Unhandled error:", repr(e))
        # Telegram expects 200 quickly; still return 200 to avoid retries storm
        return {"statusCode": 200, "body": "ok"}
