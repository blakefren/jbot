# Pull Litestream binary from official image
FROM litestream/litestream:0.5.11 AS litestream

# Use Python 3.14 slim image
FROM python:3.14-slim

# Set working directory
WORKDIR /app

# Install build dependencies if any packages require compilation
# jellyfish sometimes requires build tools
# tzdata required for ZoneInfo lookup
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Copy Litestream binary from build stage
COPY --from=litestream /usr/local/bin/litestream /usr/local/bin/litestream

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Set timezone
ENV TZ=America/Los_Angeles
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Copy the rest of the application
COPY . .

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

# Run via Litestream entrypoint
CMD ["/app/entrypoint.sh"]
