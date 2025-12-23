FROM python:3.12-slim

WORKDIR /app

# Install build tools for tgcrypto
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot code
COPY bot.py .

# Create downloads directory
RUN mkdir -p downloads

# Run the bot
CMD ["python", "bot.py"]
