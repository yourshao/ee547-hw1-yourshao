FROM python:3.11-slim
WORKDIR /app
COPY arxiv_processor.py /app/
RUN mkdir -p /data/output
ENTRYPOINT ["python", "/app/arxiv_processor.py"]