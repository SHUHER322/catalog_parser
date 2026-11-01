# Рецепт «коробки» с парсером: Python + Scrapy. Браузер не нужен — образ лёгкий
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Сначала только зависимости: при правке кода Docker не будет ставить их заново
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY catalog/ ./catalog/
COPY sites/ ./sites/

# Результаты и данные для продолжения после обрыва — снаружи контейнера
VOLUME ["/app/output", "/app/data"]

# docker run ... catalog_parser ССЫЛКА [--limit N] — всё после имени образа идёт парсеру
ENTRYPOINT ["python", "-m", "catalog"]
CMD ["--help"]
