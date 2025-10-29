# backend/Dockerfile

# 1. Temel İmaj
FROM python:3.11-slim

# 2. Ortam Değişkenleri
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 3. Gerekli OS paketlerini kur (PostgreSQL bağlantısı için)
RUN apt-get update \
    && apt-get -y install libpq-dev gcc \
    && apt-get clean

# 4. Çalışma dizini oluştur
WORKDIR /app

# 5. Bağımlılıkları kur
COPY requirements.txt .
RUN pip install -r requirements.txt

# 6. Proje kodunu kopyala
COPY . .

# Not: Gunicorn komutu veya collectstatic docker-compose.prod.yml
# üzerinden verilecek, çünkü local'de Gunicorn kullanmayacağız.