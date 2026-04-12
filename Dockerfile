FROM python:3.12-slim

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .

ENV TOYBARU_DATA_DIR=/data
EXPOSE 8099

CMD ["toybaru", "dashboard", "--host", "0.0.0.0"]
