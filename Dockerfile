# Becca on Hugging Face Spaces (Docker). HF serves the app on port 7860.
FROM python:3.11-slim

WORKDIR /app

# Writable cache/home for the non-root user HF uses
ENV HOME=/app PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 7860
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
