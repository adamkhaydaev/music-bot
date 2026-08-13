from fastapi import FastAPI
import random

app = FastAPI()

@app.get("/")
def root():
    return {"message": "Music bot is alive!"}

@app.get("/generate")
def generate(prompt: str):
    # Список фейковых ссылок для демонстрации
    fake_tracks = [
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3"
    ]
    
    return {
        "status": "success",
        "prompt": prompt,
        "track_url": random.choice(fake_tracks)
    }
