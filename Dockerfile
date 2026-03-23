FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY src /app/src
COPY data /app/data

ENV PYTHONPATH=/app/src
ENV PORT=8080

CMD ["uvicorn", "tt133_mvp.web_api:app", "--host", "0.0.0.0", "--port", "8080"]
