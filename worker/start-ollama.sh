#!/bin/bash
# start-ollama.sh
# Script to pull models and start Ollama server

# Make the script exit on any error
set -e

# Get worker ID and model name from environment variables or use defaults
WORKER_ID=${WORKER_ID:-1}
MODEL_NAME=${MODEL_NAME:-"phi:mini"}
GPU_MEMORY_LIMIT=${GPU_MEMORY_LIMIT:-2048}

# Set up logging
LOG_FILE="/results/fragments/ollama_${WORKER_ID}.log"
mkdir -p $(dirname $LOG_FILE)

# Function to log messages with timestamps
log() {
    echo "$(date +'%Y-%m-%d %H:%M:%S') - $1" | tee -a $LOG_FILE
}

# Check if Ollama is already running
if pgrep -x "ollama" > /dev/null; then
    log "Ollama is already running. Stopping it first..."
    pkill -f "ollama" || true
    sleep 2
fi

# Ensure Ollama isn't running
#pkill -f "ollama" 2>/dev/null || true
#sleep 1

# Pull the model
#log "Pulling model: ${MODEL_NAME}"
#ollama pull ${MODEL_NAME} 2>&1 | tee -a $LOG_FILE

# List available models to verify the pull was successful
#log "Listing available models:"
#ollama list 2>&1 | tee -a $LOG_FILE

# Set GPU memory limits
export OLLAMA_GPU_LAYERS=-1
export OLLAMA_GPU_MEMORY=${GPU_MEMORY_LIMIT}MiB

# Start Ollama server with memory limits
#log "Starting Ollama server with GPU memory limit: ${GPU_MEMORY_LIMIT}MB"
#nohup ollama serve > "${LOG_FILE}.serve" 2>&1 &
#OLLAMA_PID=$!

ollama serve &

echo "Waiting for Ollama server to be active..."
while [ "$(ollama list | grep 'NAME')" == "" ]; do
  sleep 1
done


log "Pulling model: ${MODEL_NAME}"
ollama pull ${MODEL_NAME} 2>&1 | tee -a $LOG_FILE

# List available models to verify the pull was successful
log "Listing available models:"
ollama list 2>&1 | tee -a $LOG_FILE

# Wait for Ollama to start
log "Waiting for Ollama server to start (PID: $OLLAMA_PID)..."
max_attempts=30
attempt=0
success=false

while [ $attempt -lt $max_attempts ]; do
    attempt=$((attempt+1))
    
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        log "Ollama server is running!"
        # List models again to verify the server is working properly
        log "Available models on the server:"
        curl -s http://localhost:11434/api/tags | jq . 2>&1 | tee -a $LOG_FILE || log "Failed to list models from API"
        success=true
        break
    fi
    
    # Check if the process is still running
    if ! ps -p $OLLAMA_PID > /dev/null; then
        log "ERROR: Ollama process died. Checking logs..."
        tail -n 20 "${LOG_FILE}.serve" | tee -a $LOG_FILE
        break
    fi
    
    log "Waiting for Ollama server (attempt $attempt/$max_attempts)..."
    sleep 2
done

if [ "$success" = true ]; then
    log "Ollama setup completed successfully"
    exit 0
else
    log "ERROR: Failed to start Ollama server after $max_attempts attempts"
    exit 1
fi
