import os
import requests
from fastapi import FastAPI, Request
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)

app = FastAPI()

# Получаем токены из переменных окружения Render
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SUNO_API_KEY = os.getenv("SUNO_API_KEY")

# URL для отправки сообщений в Telegram
TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

@app.get("/")
def root():
    return {"message": "Telegram bot is alive!"}

@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        logging.info(f"Получено обновление: {data}")

        # Проверяем, есть ли сообщение от пользователя
        if "message" in data:
            chat_id = data["message"]["chat"]["id"]
            text = data["message"].get("text", "")

            # Если пользователь написал /start
            if text == "/start":
                reply = "Привет! Я музыкальный бот. Отправь мне любой текст, и я попробую сгенерировать для тебя трек через Suno API! 🎵"
                requests.post(TELEGRAM_URL, json={"chat_id": chat_id, "text": reply})
                return {"status": "ok"}

            # Если пользователь отправил текст (промпт)
            elif text:
                # Сообщаем, что начали генерацию
                requests.post(TELEGRAM_URL, json={
                    "chat_id": chat_id, 
                    "text": "🎧 Начинаю генерацию музыки по твоему запросу, подожди немного..."
                })

                # Отправляем запрос в Suno API
                try:
                    suno_url = "https://api.suno.ai/v1/generate"  # Уточните URL!
                    headers = {
                        "Authorization": f"Bearer {SUNO_API_KEY}",
                        "Content-Type": "application/json"
                    }
                    payload = {"prompt": text, "duration": 30}
                    
                    response = requests.post(suno_url, json=payload, headers=headers, timeout=60)
                    data_suno = response.json()
                    
                    # Предположим, что ссылка лежит в поле "audio_url" (уточните по документации!)
                    track_url = data_suno.get("audio_url", "Ссылка не найдена :(")
                    
                    # Отправляем результат пользователю
                    requests.post(TELEGRAM_URL, json={
                        "chat_id": chat_id,
                        "text": f"✅ Готово! Вот твой трек:\n{track_url}"
                    })
                    
                except Exception as e:
                    requests.post(TELEGRAM_URL, json={
                        "chat_id": chat_id,
                        "text": f"❌ Ошибка при генерации: {str(e)}"
                    })
                
                return {"status": "ok"}

        return {"status": "ignored"}
    except Exception as e:
        logging.error(f"Ошибка: {str(e)}")
        return {"status": "error"}
