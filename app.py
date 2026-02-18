import os
import requests
from flask import Flask, request
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

app = Flask(__name__)

VERIFY_TOKEN = os.getenv("FB_VERIFY_TOKEN", "")
PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN", "")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "")
AI_ENABLED  = os.getenv("AI_ENABLED", "true").lower() == "true"

client = OpenAI(api_key=OPENAI_API_KEY)

GRAPH_URL = "https://graph.facebook.com/v19.0/me/messages"

@app.get("/health")
def health_check():
    return "OK", 200

@app.get("/webhook")
def verify_webhook():
    # Meta webhook verification handshake
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Verification failed", 403


@app.post("/webhook")
def handle_webhook():
    data = request.get_json(silent=True) or {}

    # Messenger page events come as object=page
    if data.get("object") != "page":
        return "OK", 200

    for entry in data.get("entry", []):
        for event in entry.get("messaging", []):
            sender_id = event.get("sender", {}).get("id")
            if not sender_id:
                continue

            msg = event.get("message", {})

            # Ignore echoes of messages your Page sent
            if msg.get("is_echo"):
                continue

            text = msg.get("text")

            # If user sent non-text (image, sticker, etc.)
            if not text:
                send_text(sender_id, "Thanks! Can you send that as text so I can help?")
                continue

            # Optional: typing indicator
            send_sender_action(sender_id, "typing_on")

            if (not AI_ENABLED):
                send_text(sender_id, "Thanks for your message! We'll get back to you soon.")
                continue
            
            reply = generate_reply(text)

            send_sender_action(sender_id, "typing_off")
            send_text(sender_id, reply)

    return "OK", 200


def generate_reply(user_text: str) -> str:
    system = (
        "You are a helpful customer support assistant for a business Facebook Page. "
        "Be friendly and concise. Ask one clarifying question if needed. "
        "Do not invent prices, policies, or order details."
    )

    resp = client.responses.create(
        model=OPENAI_MODEL,
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ],
    )

    out = (getattr(resp, "output_text", "") or "").strip()
    return out if out else "Thanks! How can I help?"


def send_sender_action(psid: str, action: str) -> None:
    payload = {"recipient": {"id": psid}, "sender_action": action}
    r = requests.post(
        GRAPH_URL,
        params={"access_token": PAGE_ACCESS_TOKEN},
        json=payload,
        timeout=10,
    )
    if not r.ok:
        print("Sender action error:", r.status_code, r.text)


def send_text(psid: str, text: str) -> None:
    payload = {
        "recipient": {"id": psid},
        "messaging_type": "RESPONSE",
        "message": {"text": text},
    }
    r = requests.post(
        GRAPH_URL,
        params={"access_token": PAGE_ACCESS_TOKEN},
        json=payload,
        timeout=10,
    )
    if not r.ok:
        print("Send API error:", r.status_code, r.text)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)
