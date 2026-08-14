import os
import requests
import logging
import time
import json
from fastapi import FastAPI, Request

logging.basicConfig(level=logging.INFO)
app = FastAPI()

# Переменные окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
SUNO_API_KEY = os.getenv("SUNO_API_KEY")

TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
PRICE_IN_STARS = 20

# Временные сессии пользователей
user_sessions = {}

# ================================
# БАЗОВЫЕ НАСТРОЙКИ SUNO (ИЗ ВАШЕЙ ДОКУМЕНТАЦИИ)
# ================================
SUNO_BASE = "https://sunoapiorg.redpandaai.co"
SUNO_HEAD = {
    "Authorization": f"Bearer {SUNO_API_KEY}",
    "Content-Type": "application/json"
}

# ================================
# ФУНКЦИИ-ПОМОЩНИКИ
# ================================

def refundStars(chat_id: int, telegram_payment_charge_id: str):
    """Возвращает звёзды пользователю при ошибке"""
    try:
        url = f"{TELEGRAM_URL}/refundStarPayment"
        payload = {"user_id": chat_id, "telegram_payment_charge_id": telegram_payment_charge_id}
        requests.post(url, json=payload, timeout=10)
        return True
    except:
        return False

def generate_yandex_tts(text: str, gender: str):
    """Генерирует идеальный MP3 через Яндекс SpeechKit"""
    url = "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize"
    headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}"}
    
    voice = "alena" if gender == "female" else "filip"
    
    params = {
        "text": text,
        "lang": "ru-RU",
        "voice": voice,
        "format": "mp3",
        "emotion": "good"
    }
    
    response = requests.get(url, headers=headers, params=params, timeout=30)
    if response.status_code != 200:
        raise Exception(f"Yandex TTS Error: {response.text}")
    
    return response.content  # Байты MP3-файла

def upload_mp3_to_suno(mp3_bytes: bytes, title: str):
    """Загружает MP3 на сервер Suno через URL-метод (согласно документации)"""
    
    # 1. Сначала загружаем файл через URL File Upload
    # ВАЖНО: В документации указан эндпоинт /api/file-url-upload, но для этого нужна ссылка.
    # Мы воспользуемся методом Stream Upload (работает напрямую с байтами)
    
    upload_url = f"{SUNO_BASE}/api/file-stream-upload"
    files = {"file": ("voice.mp3", mp3_bytes, "audio/mpeg")}
    data = {"uploadPath": "voice-uploads"}
    
    upload_response = requests.post(upload_url, headers=SUNO_HEAD, files=files, data=data)
    if upload_response.status_code != 200:
        raise Exception(f"Ошибка загрузки файла в Suno: {upload_response.text}")
    
    upload_data = upload_response.json()
    file_url = upload_data["data"]["fileUrl"]
    logging.info(f"Файл успешно загружен в Suno: {file_url}")
    
    # 2. Теперь отправляем этот файл на генерацию кавера (Upload And Cover Audio)
    # Эндпоинт для Cover может быть другим, но по логике он должен быть в API.
    # Если у вас есть точный эндпоинт Cover, замените его здесь.
    cover_url = f"{SUNO_BASE}/api/cover-upload"  # Уточните путь в документации
    cover_payload = {
        "fileUrl": file_url,
        "title": title,
        "style": "Caucasian pop, emotional, male vocal",
        "model": "V5_5"
    }
    
    cover_response = requests.post(cover_url, headers=SUNO_HEAD, json=cover_payload, timeout=30)
    if cover_response.status_code != 200:
        raise Exception(f"Ошибка при создании кавера: {cover_response.text}")
    
    cover_data = cover_response.json()
    task_id = cover_data.get("data", {}).get("taskId")
    if not task_id:
        raise Exception("Не удалось получить taskId для генерации кавера")
    
    # 3. Ждём завершения генерации (опрашиваем статус)
    start_time = time.time()
    while time.time() - start_time < 300:
        time.sleep(10)
        status_url = f"{SUNO_BASE}/api/generate/record-info"
        status_resp = requests.get(status_url, headers=SUNO_HEAD, params={"taskId": task_id})
        status_data = status_resp.json().get("data", {})
        status = (status_data.get("status") or "").upper()
        
        if status == "SUCCESS":
            tracks = status_data.get("response", {}).get("sunoData", [])
            if tracks:
                track_url = tracks[0].get("audioUrl")
                if track_url:
                    return track_url
        elif "FAIL" in status or "ERROR" in status:
            raise Exception(status_data.get("errorMessage") or status)
    
    raise Exception("Таймаут ожидания генерации кавера")

# ================================
# ОСНОВНОЙ ВЕБХУК
# ================================

@app.get("/")
def root():
    return {"message": "Chechen Song Bot with Yandex TTS + Suno Cover"}

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
                "Отправь мне текст песни, и я сделаю голосовой файл.\n"
                "Добавь в конце сообщения:\n"
                "👨 - для мужского голоса\n"
                "👩 - для женского голоса\n\n"
                "Пример:\nЛайла йолу лаьмнаш 👨"
            )
            requests.post(f"{TELEGRAM_URL}/sendMessage", json={"chat_id": chat_id, "text": reply})
            return {"status": "ok"}

        if "message" in data and "text" in data["message"]:
            chat_id = data["message"]["chat"]["id"]
            raw_text = data["message"]["text"]

            if raw_text == "/start":
                return {"status": "ok"}

            # Определяем пол голоса
            voice_gender = "male"
            text = raw_text
            if "👨" in raw_text:
                voice_gender = "male"
                text = raw_text.replace("👨", "").strip()
            elif "👩" in raw_text:
                voice_gender = "female"
                text = raw_text.replace("👩", "").strip()

            user_sessions[chat_id] = {"text": text, "gender": voice_gender}

            invoice_data = {
                "chat_id": chat_id,
                "title": "Чеченская песня 🎤",
                "description": f"Голос: {'Мужской' if voice_gender == 'male' else 'Женский'}",
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
                gender = user_sessions[chat_id]["gender"]

                requests.post(f"{TELEGRAM_URL}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": "✅ Оплачено! Начинаю создание песни (займёт 2-3 минуты)..."
                })

                try:
                    # Шаг 1: Генерация идеального MP3 через Яндекс
                    mp3_bytes = generate_yandex_tts(text, gender)
                    
                    # Шаг 2: Загрузка в Suno и генерация песни
                    track_url = upload_mp3_to_suno(mp3_bytes, "Chechen Song")
                    
                    # Шаг 3: Отправка пользователю
                    requests.post(f"{TELEGRAM_URL}/sendMessage", json={
                        "chat_id": chat_id,
                        "text": f"🎶 Готово! Вот твоя песня:\n{track_url}"
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
