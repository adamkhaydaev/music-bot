from fastapi import FastAPI, HTTPException
import requests
import os

app = FastAPI()

# Безопасно получаем ключ из переменных окружения Render
SUNO_API_KEY = os.getenv("SUNO_API_KEY")

# Если ключа нет, бот всё равно запустится, но выдаст ошибку при генерации
if not SUNO_API_KEY:
    print("⚠️ ВНИМАНИЕ: Не найден SUNO_API_KEY. Добавьте его в Environment Variables!")

@app.get("/")
def root():
    return {"message": "Music bot is alive! (Suno ready)"}

@app.get("/generate")
def generate(prompt: str):
    if not prompt:
        raise HTTPException(status_code=400, detail="Пожалуйста, укажите prompt")
    
    if not SUNO_API_KEY:
        raise HTTPException(status_code=500, detail="API ключ не настроен на сервере")
    
    try:
        # ❗ ВНИМАНИЕ: Эндпоинты и формат Suno могут меняться!
        # Проверьте актуальную документацию Suno API.
        # Ниже примерный формат (уточните по вашей документации):
        url = "https://api.suno.ai/v1/generate"  
        
        headers = {
            "Authorization": f"Bearer {SUNO_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "prompt": prompt,
            "duration": 30,
            "style": "pop"  # можно заменить на любой стиль
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        
        # Если Suno возвращает не 200, выбрасываем ошибку
        response.raise_for_status()
        
        data = response.json()
        
        return {
            "status": "success",
            "prompt": prompt,
            "track_url": data.get("audio_url"),  # Поле зависит от ответа Suno!
            "raw_response": data  # На всякий случай, чтобы посмотреть структуру
        }
        
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="API Suno не ответил за 60 секунд")
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Ошибка запроса к Suno: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Неизвестная ошибка: {str(e)}")
