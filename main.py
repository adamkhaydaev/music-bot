def upload_mp3_to_suno(mp3_bytes: bytes, title: str):
    upload_url = f"{SUNO_BASE}/api/file-stream-upload"
    
    files = {"file": ("voice.mp3", mp3_bytes, "audio/mpeg")}
    data = {
        "uploadPath": "voice-uploads",
        "fileName": "voice.mp3",
        "title": title,
        "style": "Caucasian pop, emotional, male vocal",
        "model": "V5_5"
    }
    
    # ВАЖНО: Убираем SUNO_HEAD. requests сам поставит Content-Type: multipart/form-data
    upload_response = requests.post(upload_url, data=data, files=files)
    
    if upload_response.status_code != 200:
        raise Exception(f"Ошибка загрузки файла в Suno: {upload_response.text}")
    
    upload_data = upload_response.json()
    file_url = upload_data.get("data", {}).get("fileUrl")
    if not file_url:
        logging.error(f"НЕОЖИДАННЫЙ ОТВЕТ SUNO: {upload_data}")
        raise Exception("Suno вернул неожиданную структуру ответа. Смотрите логи.")
    
    logging.info(f"Файл успешно загружен в Suno: {file_url}")
    
    cover_url = f"{SUNO_BASE}/api/cover-upload"
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
