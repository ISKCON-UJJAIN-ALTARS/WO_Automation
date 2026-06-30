# Divine Sky Work Order backend — Docker build for Render.
#
# Render's native Python runtime build step runs with a read-only system
# filesystem, so apt-get cannot install OS-level packages there (this is why
# `apt-get install tesseract-ocr` failed as a Build Command). Docker gives us
# a normal writable image during build, so Tesseract can be installed
# properly here instead.

FROM python:3.12-slim

# Install Tesseract OCR (system package, required by pytesseract) and clean
# up apt's cache afterward to keep the final image smaller.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first so this layer is cached across rebuilds
# that only change application code, not requirements.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the rest of the application.
COPY . .

# Render injects $PORT at runtime; default to 8000 for local `docker run`.
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
