
FROM python:3.11

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir fastapi uvicorn sqlalchemy psycopg2-binary jinja2 python-multipart qrcode PIL 

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
