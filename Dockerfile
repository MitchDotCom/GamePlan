# Recognition engine: one process, one SQLite file on a persistent volume mounted at /data.
ARG BASE=python:3.11-slim
FROM ${BASE}
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app/src ENGINE_DATA=/data TRUST_PROXY=1
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir numpy scipy fastapi==0.115.0 "uvicorn==0.30.6" jinja2==3.1.6 segno==1.6.1 imageio-ffmpeg==0.6.0 httpx==0.27.2
COPY src ./src
COPY phone_app ./phone_app
COPY config ./config
COPY deploy/entrypoint.sh /entrypoint.sh
RUN useradd -m engine && mkdir -p /data && chmod +x /entrypoint.sh
EXPOSE 8080
# Exactly one worker: the scheduler, throttles and SQLite writer all assume a single process.
ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "gameplan.engine.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
