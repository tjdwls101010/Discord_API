FROM python:3.12-slim
WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    curl \
    unzip \
    ca-certificates \
    libicu-dev \
 && rm -rf /var/lib/apt/lists/*

ARG DCE_VERSION=2.46
RUN curl -L -o /tmp/dce.zip "https://github.com/Tyrrrz/DiscordChatExporter/releases/download/${DCE_VERSION}/DiscordChatExporter.Cli.Linux-x64.zip" \
 && unzip /tmp/dce.zip -d /opt/dce \
 && chmod +x /opt/dce/DiscordChatExporter.Cli \
 && rm /tmp/dce.zip

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


