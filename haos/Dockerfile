FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
COPY run.py .
RUN ln -s /data/config.json /app/config.json && ln -s /data/history /app/data
CMD ["python", "/app/run.py"]
