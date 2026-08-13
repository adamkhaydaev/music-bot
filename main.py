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
PRICE_IN_STARS = 10

# Хранилище временных данных пользователей (в памяти)
# В реальном проекте лучше использовать Redis или базу данных
user_sessions = {}

@app.get("/")
def root():
    return {"message": "Telegram bot with Stars payment is alive!"}

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

            # Игнорируем команду /start, если она уже обработана выше
            if prompt == "/start":
                return {"status": "ok"}

            # Сохраняем промпт в сессию пользователя
            user_sessions[chat_id] = {"prompt": prompt, "paid": False}

            # Создаём инвойс для оплаты звёздами
            invoice_data = {
                "chat_id": chat_id,
                "title": "Генерация музыки через Suno AI 🎵",
                "description": f"Создание трека по запросу: '{prompt[:30]}...'",
                "payload": f"generate_{chat_id}",
                "currency": "XTR",  # XTR = Telegram Stars
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
            
            # Помечаем, что пользователь оплатил
            if chat_id in user_sessions:
                user_sessions[chat_id]["paid"] = True
                prompt = user_sessions[chat_id]["prompt"]
                
                # Отправляем сообщение о начале генерации
                requests.post(f"{TELEGRAM_URL}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": "✅ Оплата получена! 🎧 Начинаю генерацию музыки, подожди немного..."
                })

                # --- ВЫЗОВ SUNO API ---
                try:
                    # Проверьте актуальный URL и payload в документации Suno!
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
                    
                    suno_response = requests.post(suno_url, json=payload, headers=headers, timeout=60)
                    suno_data = suno_response.json()
                    
                    track_url = suno_data.get("audio_url", "Ссылка не найдена :(")
                    
                    # Отправляем результат пользователю
                    requests.post(f"{TELEGRAM_URL}/sendMessage", json={
                        "chat_id": chat_id,
                        "text": f"🎶 Готово! Вот твой трек:\n{track_url}"
                    })
                    
                except Exception as e:
                    requests.post(f"{TELEGRAM_URL}/sendMessage", json={
                        "chat_id": chat_id,
                        "text": f"❌ Ошибка при генерации: {str(e)}"
                    })
                
                # Очищаем сессию после генерации
                if chat_id in user_sessions:
                    del user_sessions[chat_id]
                
                return {"status": "ok"}

        return {"status": "ignored"}
    except Exception as e:
        logging.error(f"Ошибка: {str(e)}")
        return {"status": "error"}
