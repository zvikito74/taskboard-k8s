FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# Numeric user ID, so Kubernetes can verify the container is not root
RUN useradd --uid 10001 --create-home appuser
USER 10001

EXPOSE 8000

# Gunicorn writes its temporary files to /tmp, which is a writable volume in Kubernetes
CMD ["gunicorn", "--workers", "2", "--bind", "0.0.0.0:8000", "--worker-tmp-dir", "/tmp", "app:create_app()"]
