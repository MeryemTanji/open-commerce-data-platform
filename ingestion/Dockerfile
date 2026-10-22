FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/mercury

RUN groupadd --system mercury \
    && useradd \
        --system \
        --gid mercury \
        --create-home \
        --home-dir /home/mercury \
        mercury

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src

RUN python -m pip install --no-cache-dir .

USER mercury

ENTRYPOINT ["python", "-m", "mercury_ingestion.cli"]
CMD ["--help"]