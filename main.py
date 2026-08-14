import os
import requests
import json
import time
import logging
from fastapi import FastAPI, Request

# Настройка логирования
logging.basicConfig(level=logging.INFO)

app = FastAPI()

# Получаем токены из переменных окружения Render
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SUNO_API_KEY = os.getenv("SUNO_API_KEY")

# URL для отправки сообщений в Telegram
TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# Цена за одну генерацию (в звёздах)
PRICE_IN_STARS = 10

# Хранилище временных данных пользователей
user_sessions = {}

# Базовый URL и заголовки для Suno API (как в вашем коде)
BASE = "https://api.sunoapi.org"
HEAD = {
    "Authorization": f"Bearer {SUNO_API_KEY}",
    "Content-Type": "application/json"
}

def refundStars(chat_id: int, telegram_payment_charge_id: str):
    """Возвращает звёзды пользователю при ошибке"""
    try:
        url = f"{TELEGRAM_URL}/refundStarPayment"
        payload = {
            "user_id": chat_id,
            "telegram_payment_charge_id": telegram_payment_charge_id
        }
        response = requests.post(url, json=payload, timeout=10)
        logging.info(f"Ответ на возврат звёзд: {response.json()}")
        return response.ok
    except Exception as e:
        logging.error(f"Ошибка при возврате звёзд: {str(e)}")
        return False

def generate_song(lyrics: str):
    """Отправляет запрос на генерацию и ждёт результат"""
    try:
        # Шаг 1: Отправляем запрос на генерацию
        body = {
            "prompt": lyrics,
            "style": "pop, male vocal, emotional",
            "title": "My Song",
            "customMode": True,
            "instrumental": False,
            "model": "V5_5",
            "vocalGender": "m",
            "callBackUrl": "https://example.com/callback"
        }
        
        logging.info("Отправляем запрос на генерацию...")
        resp = requests.post(f"{BASE}/api/v1/generate", headers=HEAD, json=body, timeout=30).json()
        logging.info(f"Ответ на генерацию: {resp}")
        
        if resp.get("code") != 200:
            raise Exception(f"Ошибка при старте генерации: {resp.get('msg')}")
        
        task_id = resp["data"]["taskId"]
        logging.info(f"Получен taskId: {task_id}")
        
        # Шаг 2: Ждём, пока трек сгенерируется (опрашиваем каждые 12 секунд)
        start_time = time.time()
        while time.time() - start_time < 360:  # Ждём максимум 6 минут
            time.sleep(12)
            
            status_resp = requests.get(
                f"{BASE}/api/v1/generate/record-info", 
                headers=HEAD,
                params={"taskId": task_id}, 
                timeout=30
            ).json()
            
            data = status_resp.get("data", {})
            status = (data.get("status") or "").upper()
            
            logging.info(f"Статус задачи: {status}")
            
            if status == "SUCCESS":
                r = data.get("response", {}) or {}
                tracks = r.get("sunoData") or r.get("data") or []
                if tracks:
                    track_url = tracks[0].get("audioUrl") or tracks[0].get("audio_url")
                    if track_url:
                        return track_url
                    raise Exception("Трек получен, но ссылка не найдена")
            
            if "FAIL" in status or "ERROR" in status:
                raise Exception(data.get("errorMessage") or status)
        
        raise Exception("Таймаут генерации (превышено время ожидания)")
    
    except Exception as e:
        logging.error(f"Ошибка генерации: {str(e)}")
        raise e

@app.get("/")
def root():
    return {"message": "Telegram bot with Suno AI generation is alive!"}

@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        logging.info(f"Получено обновление: {data}")

        # Обработка команды /start
        if "message" in data and data["message"].get("text") == "/start":
            chat_id = data["message"]["chat"]["id"]
            reply = (
                "🎵 Привет! Я музыкальный бот.\n\n"
                f"Стоимость генерации одного трека: {PRICE_IN_STARS} ⭐ Telegram Stars.\n\n"
                "Просто отправь мне текст песни (промпт), и я пришлю счёт на оплату."
            )
            requests.post(f"{TELEGRAM_URL}/sendMessage", json={"chat_id": chat_id, "text": reply})
            return {"status": "ok"}

        # Обработка текстового сообщения (промпт)
        if "message" in data and "text" in data["message"]:
            chat_id = data["message"]["chat"]["id"]
            prompt = data["message"]["text"]

            if prompt == "/start":
                return {"status": "ok"}

            # Сохраняем промпт в сессию
            user_sessions[chat_id] = {"prompt": prompt}

            # Создаём инвойс для оплаты звёздами
            invoice_data = {
                "chat_id": chat_id,
                "title": "Генерация музыки через Suno AI 🎵",
                "description": f"Создание трека по запросу: '{prompt[:30]}...'",
                "payload": f"generate_{chat_id}",
                "currency": "XTR",
                "prices": [{"label": "Генерация 1 трека", "amount": PRICE_IN_STARS}],
                "need_name": False,
                "need_phone_number": False,
                "need_email": False,
                "need_shipping_address": False
            }

            response = requests.post(f"{TELEGRAM_URL}/sendInvoice", json=invoice_data)
            logging.info(f"Ответ sendInvoice: {response.json()}")
            return {"status": "invoice_sent"}

        # Обработка успешной оплаты (PreCheckoutQuery)
        if "pre_checkout_query" in data:
            query_id = data["pre_checkout_query"]["id"]
            requests.post(f"{TELEGRAM_URL}/answerPreCheckoutQuery", json={
                "pre_checkout_query_id": query_id,
                "ok": True
            })
            return {"status": "ok"}

        # Обработка подтверждения оплаты (Message с successful_payment)
        if "message" in data and "successful_payment" in data["message"]:
            chat_id = data["message"]["chat"]["id"]
            telegram_payment_charge_id = data["message"]["successful_payment"]["telegram_payment_charge_id"]

            if chat_id in user_sessions:
                prompt = user_sessions[chat_id]["prompt"]
                
                requests.post(f"{TELEGRAM_URL}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": "✅ Оплата получена! 🎧 Начинаю генерацию, это займёт до 2–3 минут..."
                })

                try:
                    # Запускаем генерацию
                    track_url = generate_song(prompt)
                    
                    # Отправляем результат пользователю
                    requests.post(f"{TELEGRAM_URL}/sendMessage", json={
                        "chat_id": chat_id,
                        "text": f"🎶 Готово! Вот твой трек:\n{track_url}"
                    })

                except Exception as e:
                    logging.error(f"Ошибка генерации: {str(e)}")
                    
                    # Возвращаем звёзды
                    refundStars(chat_id, telegram_payment_charge_id)
                    
                    requests.post(f"{TELEGRAM_URL}/sendMessage", json={
                        "chat_id": chat_id,
                        "text": "❌ Ошибка при генерации. Звёзды возвращены. Попробуй позже или измени текст."
                    })

                # Удаляем сессию
                if chat_id in user_sessions:
                    del user_sessions[chat_id]

                return {"status": "ok"}

        return {"status": "ignored"}
    except Exception as e:
        logging.error(f"Ошибка webhook: {str(e)}")
        return {"status": "error"}
