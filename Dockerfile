FROM python:3.11-slim

# Set timezone (Highly recommended for financial/scheduler logs)
ENV TZ=Asia/Seoul

# Set working directory
WORKDIR /app

# Copy dependency manifest
COPY requirements.txt .

# Run pip install (virtually a no-op due to pure stdlib design)
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Ensure DB directory exists
RUN mkdir -p /app/data

# Expose a volume for persistent database storage
VOLUME ["/app/data"]

# Run the entry script
CMD ["python", "main.py"]
