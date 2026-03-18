FROM python:3.11-slim

WORKDIR /app

# Installer les dependances systeme pour psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV FLASK_APP=api8inf349
ENV FLASK_DEBUG=True

EXPOSE 5000

CMD ["flask", "run", "--host=0.0.0.0"]
