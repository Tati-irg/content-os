FROM python:3.12-slim

WORKDIR /app
COPY coordinator /app/coordinator

ENV PYTHONUNBUFFERED=1
CMD ["python3", "coordinator/railway_start.py"]
