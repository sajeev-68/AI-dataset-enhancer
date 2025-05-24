# Dockerfile for Master Container
# Save this as master/Dockerfile

FROM python:3.9-slim

# Install dependencies
RUN pip install requests tqdm

# Create directories for data and results
WORKDIR /app
RUN mkdir -p /data /results

# Copy master script
COPY master.py /app/master.py
RUN chmod +x /app/master.py

# Run the master script
CMD ["python", "/app/master.py"]
