# DHARANI 360 - portable container.
# Runs the same way on your own PC, a company server, a VPS, or any
# host that speaks Docker. Nothing here is tied to one provider.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=5000

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Records, uploads, staff photos and the signing key live here.
# docker-compose mounts a named volume over it so they survive a rebuild.
RUN mkdir -p /app/instance
VOLUME ["/app/instance"]

EXPOSE 5000

# SQLite is happy with many threads in one process and unhappy with several
# processes writing at once, so the default stays at one worker. With
# DATABASE_URL pointing at Postgres, raise it - GUNICORN_WORKERS is read at
# start-up, so no rebuild is needed:
#     docker run -e DATABASE_URL=... -e GUNICORN_WORKERS=4 ...
ENV GUNICORN_WORKERS=1 GUNICORN_THREADS=8

CMD ["sh", "-c", "exec gunicorn app:app \
     --bind 0.0.0.0:${PORT:-5000} \
     --workers ${GUNICORN_WORKERS:-1} --threads ${GUNICORN_THREADS:-8} \
     --timeout 120 --access-logfile - --error-logfile -"]
