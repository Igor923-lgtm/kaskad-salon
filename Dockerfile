FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py db.py config.py api.py price_data.py ./
COPY templates/ templates/
COPY static/ static/
RUN cp static/logo.png static/salon_logo.png 2>/dev/null || true
COPY price.json ./
COPY salons/ salons/

RUN mkdir -p master_photos works_photos data

EXPOSE 8000

CMD ["sh", "-c", "python -m uvicorn api:app --host 0.0.0.0 --port 8000 & python bot.py"]