FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd -r -u 1000 -d /opt/bitunix-dashboard scanner
WORKDIR /opt/bitunix-dashboard
COPY app/server.py app/index.html ./
COPY data/ ./
USER scanner
EXPOSE 8124
CMD ["python3", "server.py"]
