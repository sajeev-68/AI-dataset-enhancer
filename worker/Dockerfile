# Dockerfile for Worker Container
# Save this as worker/Dockerfile

FROM nvidia/cuda:12.1.0-base-ubuntu22.04

# Install Python and dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    curl \
    wget \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages
RUN pip3 install requests tqdm ollama

# Install Ollama
RUN curl -fsSL https://ollama.com/install.sh | sh

# Create directories for data and results
WORKDIR /app
RUN mkdir -p /data /results/fragments

# Copy worker script and Ollama start script
COPY worker.py /app/worker.py
COPY start-ollama.sh /app/start-ollama.sh
RUN chmod +x /app/worker.py /app/start-ollama.sh

# Run the worker script
CMD ["python3", "/app/worker.py"]
