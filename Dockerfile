FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SCRUBPUP_HOME=/data

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml ./
RUN pip install -r requirements.txt

COPY main.py ./
COPY scrubpup ./scrubpup
COPY config.example.yaml ./
RUN pip install --no-deps -e .

VOLUME ["/data"]
WORKDIR /data

ENTRYPOINT ["scrubpup"]
CMD ["--help"]
