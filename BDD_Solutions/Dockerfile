# Use a minimal Python base image
FROM python:3.10-slim

# Set environment variables to prevent Python from writing .pyc files and to run in an unbuffered mode
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install required build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    gcc \
    g++ \
    python3-dev \
    libffi-dev \
    libxml2-dev \
    libxslt-dev \
    make
# Set the working directory in the container
WORKDIR /app

# Copy only the requirements file first (improve caching)
COPY requirements.txt .

# Upgrade pip and install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose the application port
EXPOSE 5000

# Run the Flask app with Gunicorn
CMD ["gunicorn", "-b", "0.0.0.0:5000", "app:app"]