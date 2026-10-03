# Build stage
FROM python:3.11-slim AS build

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim AS production

WORKDIR /app

COPY --from=build /install /usr/local

RUN mkdir -p /app/data
VOLUME ["/app/data"]

COPY . .

ENV FLASK_ENV=production \
  PYTHONUNBUFFERED=1 \
  DATABASE_URL=sqlite:////app/data/app.db \
  PORT=5000

EXPOSE 5000

RUN chown -R 1000:1000 /app
USER 1000

CMD ["waitress-serve", "--port=5000", "run:app"]

