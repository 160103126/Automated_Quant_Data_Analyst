FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY market_analyst ./market_analyst
COPY skills ./skills

ENV MCP_GATEWAY_URL=http://host.docker.internal:8000
ENV REPORT_DIRECTORY=/data/fs/reports
ENV REPORT_TIMEZONE=Asia/Calcutta

EXPOSE 8080

CMD ["uvicorn", "market_analyst.main:app", "--host", "0.0.0.0", "--port", "8080"]
