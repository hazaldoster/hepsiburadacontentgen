FROM python:3.9-slim

WORKDIR /app

# Install system dependencies and build tools
RUN apt-get update && apt-get install -y \
    nodejs \
    npm \
    build-essential \
    libffi-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy package.json and install Node dependencies
COPY package.json .
RUN npm install

# Copy the rest of the application
COPY . .

# Expose the port the app runs on
EXPOSE 5000

# Start the application
CMD ["python", "app.py"] 