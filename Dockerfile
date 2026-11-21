FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 CTW_DATA_DIR=/app/data
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && useradd -u 10001 -m runner && mkdir /app/data && chown runner:runner /app/data
COPY app.py main.py ./
COPY static ./static
USER runner
EXPOSE 8765
CMD ["python", "main.py"]
