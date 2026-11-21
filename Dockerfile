FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 CTW_DATA_DIR=/app/data
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && adduser --disabled-password --gecos '' appuser \
    && mkdir -p /app/data && chown -R appuser:appuser /app/data
COPY app.py /app/app.py
COPY static /app/static
USER appuser
EXPOSE 8765
CMD ["python","-m","uvicorn","app:app","--host","0.0.0.0","--port","8765","--workers","1"]
