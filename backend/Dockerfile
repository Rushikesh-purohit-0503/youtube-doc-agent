FROM python:3.11-slim

WORKDIR /app

# ffmpeg required for yt-dlp audio extraction (Whisper fallback)
# deno required for yt-dlp JS runtime (YouTube bot detection bypass)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl unzip \
    && curl -fsSL https://deno.land/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

ENV DENO_INSTALL="/root/.deno"
ENV PATH="${DENO_INSTALL}/bin:${PATH}"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Pre-create volume mount points
RUN mkdir -p /app/pdfs /app/db

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
