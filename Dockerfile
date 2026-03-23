# Base image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy files
COPY . .

# Install dependencies
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Expose port (must match config.PORT / app.run)
ENV PORT=5050
EXPOSE 5050

# Run Flask app
CMD ["python", "app.py"]
