# FreeAir Bridge - Python Application in Docker
FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config_manager.py .
COPY web_admin.py .
COPY crypto_utils.py .
COPY utils.py .
COPY freeair_parser.py .
COPY loxone_xml.py .
COPY data_parser.py .

COPY static/ ./static/
COPY templates/ ./templates/
COPY config/FreeAir2Lox_config.example.json ./config/

RUN mkdir -p /app/config

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 -c "import socket; s=socket.socket(); s.connect(('localhost', 80)); s.close()" || exit 1

EXPOSE 80 5555 8080

ENV PUID=99 \
    PGID=100 \
    UMASK=000 \
    TZ=UTC \
    LOG_LEVEL=INFO \
    CONFIG_FILE=/app/config/FreeAir2Lox_config.json

RUN mkdir -p /app/templates_backup && \
    cp config/FreeAir2Lox_config.example.json /app/templates_backup/ && \
    echo '#!/bin/bash\n\
if [ ! -z "$PUID" ] && [ ! -z "$PGID" ]; then\n\
    groupmod -o -g $PGID root 2>/dev/null || echo "Group mod skipped"\n\
    usermod -o -u $PUID root 2>/dev/null || echo "User mod skipped"\n\
    chown -R $PUID:$PGID /app/config\n\
fi\n\
if [ ! -f /app/config/FreeAir2Lox_config.json ]; then\n\
    echo "[STARTUP] Creating initial config from example..."\n\
    cp /app/templates_backup/FreeAir2Lox_config.example.json /app/config/FreeAir2Lox_config.json\n\
    chown $PUID:$PGID /app/config/FreeAir2Lox_config.json 2>/dev/null\n\
fi\n\
exec python3 web_admin.py\n\
' > /app/entrypoint.sh && chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
