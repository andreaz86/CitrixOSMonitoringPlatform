FROM python:3.9-slim

WORKDIR /app

# Copia i requirements prima del resto del codice per sfruttare la cache di Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia il resto dell'applicazione
COPY . .

# Esponi la porta su cui girerà il servizio
EXPOSE 8000

# Comando di avvio dell'applicazione
CMD ["python", "-m", "app.main"]