FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY *.py .

# Create directories
RUN mkdir -p db models logs

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "app_local:app", "--host", "0.0.0.0", "--port", "8000"]
