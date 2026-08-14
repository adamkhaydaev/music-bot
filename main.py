import os
import requests
import json
import logging
from fastapi import FastAPI, Request, HTTPException

# Настройка логирования
logging.basicConfig(level=logging.INFO)

app = FastAPI()

# Получаем токены из переменных окружения Render
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SUNO_API_KEY = os.getenv("SUNO_API_KEY")

# URL для отправки сообщений в Telegram
TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# Цена за одну генерацию (в звёздах)
PRICE_IN_STARS = 1

user_sessions = {}

def refundStars(chat_id: int, amount: int, telegram_payment_charge_id: str):
    """
    Отправляет запрос на возврат звёзд пользователю через Telegram API.
    """
    try:
        url = f"{TELEGRAM_URL}/refundStarPayment"
        payload = {
            "user_id": chat_id,
            "telegram_payment_charge_id": telegram_payment_charge_id
        }
        response = requests.post(url, json=payload)
        logging.info(f"Ответ на возврат звёзд: {response.json()}")
        return response.ok
    except Exception as e:
        logging.error(f"Ошибка при возврате звёзд: {str(e)}")
        return False

@app.get("/")
def root():
    return {"message": "Telegram bot with Stars refund logic is alive!"}

@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        logging.info(f"Получено обновление: {data}")

        # Обработка команды /start
        if "message" in data and data["message"].get("text") == "/start":
            chat_id = data["message"]["chat"]["id"]
            reply = (
                "🎵 Привет! Я музыкальный бот с оплатой звёздами.\n\n"
                f"Стоимость одной генерации: {PRICE_IN_STARS} ⭐ Telegram Stars.\n\n"
                "Просто отправь мне текст (промпт), и я пришлю тебе счёт на оплату."
            )
            requests.post(f"{TELEGRAM_URL}/sendMessage", json={"chat_id": chat_id, "text": reply})
            return {"status": "ok"}

        # Обработка текстового сообщения (промпт)
        if "message" in data and "text" in data["message"]:
            chat_id = data["message"]["chat"]["id"]
            prompt = data["message"]["text"]

            if prompt == "/start":
                return {"status": "ok"}

            user_sessions[chat_id] = {"prompt": prompt, "paid": False}

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
                user_sessions[chat_id]["paid"] = True
                prompt = user_sessions[chat_id]["prompt"]
                
                requests.post(f"{TELEGRAM_URL}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": "✅ Оплата получена! 🎧 Начинаю генерацию музыки, подожди немного..."
                })

                try:
                    suno_url = "https://api.suno.ai/v1/generate"
                    headers = {
                        "Authorization": f"Bearer {SUNO_API_KEY}",
                        "Content-Type": "application/json"
                    }
                    payload = {
                        "prompt": prompt,
                        "duration": 30,
                        "style": "pop"
                    }
                    
                    suno_response = requests.post(suno_url, json=payload, headers=headers, timeout=30)
                    
                    logging.info(f"Статус код Suno: {suno_response.status_code}")
                    logging.info(f"Тело ответа Suno: {suno_response.text}")
                    
                    # Если ошибка -> возвращаем звёзды!
                    if suno_response.status_code != 200:
                        raise Exception(f"Suno вернул код {suno_response.status_code}: {suno_response.text}")

                    try:
                        suno_data = suno_response.json()
                    except json.JSONDecodeError:
                        raise Exception(f"Ошибка JSON: {suno_response.text[:200]}")
                    
                    track_url = suno_data.get("audio_url", "Ссылка не найдена :(")
                    
                    requests.post(f"{TELEGRAM_URL}/sendMessage", json={
                        "chat_id": chat_id,
                        "text": f"🎶 Готово! Вот твой трек:\n{track_url}"
                    })
                    
                except Exception as e:
                    logging.error(f"Ошибка при генерации: {str(e)}")
                    
                    # ВОЗВРАТ ЗВЁЗД В СЛУЧАЕ ОШИБКИ!
                    refund_result = refundStars(chat_id, PRICE_IN_STARS, telegram_payment_charge_id)
                    
                    if refund_result:
                        error_msg = f"❌ Ошибка при генерации. Мы вернули тебе {PRICE_IN_STARS} ⭐ обратно. Попробуй позже."
                    else:
                        error_msg = f"❌ Ошибка при генерации. К сожалению, не удалось автоматически вернуть звёзды. Пожалуйста, свяжист с поддержкой."
                    
                    requests.post(f"{TELEGRAM_URL}/sendMessage", json={
                        "chat_id": chat_id,
                        "text": error_msg
                    })
                
                if chat_id in user_sessions:
                    del user_sessions[chat_id]
                
                return {"status": "ok"}

        return {"status": "ignored"}
    except Exception as e:
        logging.error(f"Ошибка: {str(e)}")
        return {"status": "error"}
