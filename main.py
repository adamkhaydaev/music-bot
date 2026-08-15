import os
import requests
import logging
import time
import json
from fastapi import FastAPI, Request

logging.basicConfig(level=logging.INFO)
app = FastAPI()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
PRICE_IN_STARS = 1

user_sessions = {}

def refundStars(chat_id: int, telegram_payment_charge_id: str):
    try:
        url = f"{TELEGRAM_URL}/refundStarPayment"
        payload = {"user_id": chat_id, "telegram_payment_charge_id": telegram_payment_charge_id}
        requests.post(url, json=payload, timeout=10)
        return True
    except:
        return False

def generate_elevenlabs_song(text: str):
    # Эндпоинт ElevenLabs для генерации звука
    url = "https://api.elevenlabs.io/v1/text-to-speech/21m00Tcm4TlvDq8ikWAM"
    
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": ELEVENLABS_API_KEY
    }
    
    data = {
        "text": text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.5,
            "style": 0.3,
            "use_speaker_boost": True
        }
    }
    
    response = requests.post(url, json=data, headers=headers, timeout=60)
    if response.status_code != 200:
        raise Exception(f"ElevenLabs error: {response.text}")
    
    # Бот отправляет аудио в Telegram прямо из байтов
    files = {"audio": ("song.mp3", response.content, "audio/mpeg")}
    return files

@app.get("/")
def root():
    return {"message": "Chechen Song Bot with ElevenLabs"}

@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        logging.info(f"Update: {data}")

        if "message" in data and data["message"].get("text") == "/start":
            chat_id = data["message"]["chat"]["id"]
            reply = (
                "🎵 Привет! Я создаю песни на чеченском языке!\n\n"
                f"Стоимость: {PRICE_IN_STARS} ⭐ за трек.\n\n"
                "Отправь мне текст песни, и я сделаю готовую песню."
            )
            requests.post(f"{TELEGRAM_URL}/sendMessage", json={"chat_id": chat_id, "text": reply})
            return {"status": "ok"}

        if "message" in data and "text" in data["message"]:
            chat_id = data["message"]["chat"]["id"]
            text = data["message"]["text"]

            if text == "/start":
                return {"status": "ok"}

            user_sessions[chat_id] = {"text": text}

            invoice_data = {
                "chat_id": chat_id,
                "title": "Чеченская песня 🎤",
                "description": f"Трек по запросу: '{text[:30]}...'",
                "payload": f"tts_{chat_id}",
                "currency": "XTR",
                "prices": [{"label": "1 трек", "amount": PRICE_IN_STARS}],
            }
            requests.post(f"{TELEGRAM_URL}/sendInvoice", json=invoice_data)
            return {"status": "invoice_sent"}

        if "pre_checkout_query" in data:
            query_id = data["pre_checkout_query"]["id"]
            requests.post(f"{TELEGRAM_URL}/answerPreCheckoutQuery", json={
                "pre_checkout_query_id": query_id,
                "ok": True
            })
            return {"status": "ok"}

        if "message" in data and "successful_payment" in data["message"]:
            chat_id = data["message"]["chat"]["id"]
            charge_id = data["message"]["successful_payment"]["telegram_payment_charge_id"]

            if chat_id in user_sessions:
                text = user_sessions[chat_id]["text"]

                requests.post(f"{TELEGRAM_URL}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": "✅ Оплачено! Начинаю создание песни (займёт 30-60 секунд)..."
                })

                try:
                    song_files = generate_elevenlabs_song(text)
                    requests.post(f"{TELEGRAM_URL}/sendAudio", data={"chat_id": chat_id}, files=song_files)
                    requests.post(f"{TELEGRAM_URL}/sendMessage", json={
                        "chat_id": chat_id,
                        "text": "🎶 Готово! Вот твоя песня!"
                    })

                except Exception as e:
                    logging.error(f"Error: {e}")
                    refundStars(chat_id, charge_id)
                    requests.post(f"{TELEGRAM_URL}/sendMessage", json={
                        "chat_id": chat_id,
                        "text": "❌ Ошибка. Звёзды возвращены."
                    })

                if chat_id in user_sessions:
                    del user_sessions[chat_id]

        return {"status": "ignored"}
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return {"status": "error"}
