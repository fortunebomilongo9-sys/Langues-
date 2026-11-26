FROM python:3-alpine
# The date keys the build cache so this layer installs today's OS fixes; AppJet keeps it current on deploy.
RUN echo "os-refresh 2026-11-26" && apk upgrade --no-cache
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=8000
ENV PYTHONUNBUFFERED=1
ENV JF_DATA_DIR=/app/data
EXPOSE 8000
RUN mkdir -p /app /app/data /home/appjet && chown -R 10001:10001 /app /home/appjet
ENV HOME=/home/appjet
USER 10001:10001
CMD uvicorn backend.app.main:app --host 0.0.0.0 --port "$PORT"
