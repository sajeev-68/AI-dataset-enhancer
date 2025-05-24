# Dataset Enhancer Pipeline

A distributed system for enhancing datasets using Docker containers and Ollama LLMs with parallel processing capabilities. Reduces overall creation/enhancing time.

## 🚀 Overview

This pipeline processes large datasets of vulnerability analyses and enhances their descriptions using AI models. It's designed to handle up to 17,000+ samples efficiently through parallel processing across multiple Docker containers.

## Note 
Some things to consider:

- This pipeline uses a specific format for the json file(no csv, sorry!), but it can easily be changed in the master and worker script to suit any dataset(not only vulnerability datasets)
- The prompt used is a custom one, feel free to change the format of the prompt, the max new tokens and the temprature
- This only works for linux/wsl with nvidia gpus(with support for the cuda container toolkit)
- The code can be adapted to also create samples from scratch, but the quality depends on the model that is pulled.
- Be sure to create the data directory and add the input file.

### Key Features

- **🔄 Parallel Processing**: Distributes workload across multiple Docker containers
- **💾 Automatic Checkpointing**: Saves progress every 100 entries to prevent data loss
- **🎯 GPU Memory Management**: Efficiently shares GPU resources across workers
- **🔧 Resume Capability**: Automatically resumes from checkpoints after interruptions

## 🏗️ Architecture

The system consists of:

- **Master Container**: Coordinates workers, splits datasets, monitors progress, and combines results
- **Worker Containers**: Process individual data fragments using Ollama LLMs
- **Shared Volumes**: Enable data sharing between containers

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Master        │    │   Worker 1      │    │   Worker 2      │
│   Container     │◄──►│   Container     │    │   Container     │
│                 │    │   (Ollama +     │    │   (Ollama +     │
│   • Data Split  │    │    Model)       │    │    Model)       │
│   • Progress    │    └─────────────────┘    └─────────────────┘
│   • Combine     │              │                      │
└─────────────────┘              ▼                      ▼
                           ┌─────────────────┐    ┌─────────────────┐
                           │   Worker 3      │    │   Worker 4      │
                           │   Container     │    │   Container     │
                           │   (Ollama +     │    │   (Ollama +     │
                           │    Model)       │    │    Model)       │
                           └─────────────────┘    └─────────────────┘
```

## 📋 Prerequisites

### System Requirements

- **GPU**: NVIDIA GPU with 8GB+ VRAM (tested on RTX 4060)
- **RAM**: 16GB+ recommended
- **Storage**: ~20GB free space for models and data
- **OS**: Linux (Ubuntu 22.04+ recommended)

### Software Dependencies

- [Docker](https://docs.docker.com/get-docker/) (v20.10+)
- [Docker Compose](https://docs.docker.com/compose/install/) (v2.0+)
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)

## 🛠️ Installation

### 1. Install Docker and NVIDIA Support



```bash
# Install Docker
sudo apt-get update
sudo apt-get install docker.io docker-compose
```

For the Nvidia container toolkit please follow the [official guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)

**Note: The installation process for linux and wsl2 is different please install the proper package/driver**

Also install Docker desktop for wsl2

### 2. Clone Repository

```bash
git clone https://github.com/yourusername/vulnerability-enhancement-pipeline.git
cd vulnerability-enhancement-pipeline
```

### 3. Setup Data Directory

```bash
mkdir -p data results
# Place your dataset file in data/vulnerability_dataset.json
```

## 🚀 Quick Start

### Basic Usage

1. **Prepare your dataset**: Place your JSON dataset in `data/vulnerability_dataset.json`

2. **Start processing**:
   ```bash
   docker-compose up --build
   ```

3. **Monitor progress**: The terminal will display real-time progress for all workers

4. **Access results**: Enhanced dataset will be saved to `results/vulnerability_dataset.enhanced.json`

### Test Mode

To test with a small sample first:

```bash
# Edit docker-compose.yml and set TEST_MODE=true for workers
docker-compose up --build
```

## ⚙️ Configuration

### Docker Compose Settings

Edit `docker-compose.yml` to customize:

```yaml
environment:
  - MODEL_NAME=gemma3:1b-it-qat  # Change model
  - GPU_MEMORY_LIMIT=1536        # Adjust VRAM per worker
  - NUM_WORKERS=4                # Number of parallel workers
```

### Available Models

Recommended models for 8GB GPU:
- `gemma3:1b-it-qat` (1GB VRAM each, 4 workers)
- `qwen3:0.6b` (0.8GB VRAM each, 6-8 workers)
- `phi:mini` (1.5GB VRAM each, 3-4 workers)

### Worker Configuration

Modify `worker/worker.py` to adjust:
- Batch processing size
- Checkpoint frequency
- Prompt templates
- Processing parameters

## 📊 Monitoring

The system provides comprehensive monitoring:

```
================================================================================
VULNERABILITY ENHANCEMENT PROCESSING - 2025-05-22 10:45:23
================================================================================

OVERALL PROGRESS: 8542/17000 entries (50.2%)
--------------------------------------------------------------------------------

WORKER STATUS:
Worker 1: [██████████████████████████████] 100.0% - Completed (4250/4250)
Worker 2: [███████████████████░░░░░░░░░░░] 63.5% - Processing (2698/4250)
Worker 3: [████████░░░░░░░░░░░░░░░░░░░░░░] 28.3% - Processing (1203/4250)
Worker 4: [██░░░░░░░░░░░░░░░░░░░░░░░░░░░░] 9.2% - Processing (391/4250)

LATEST LOGS:
Worker 1: Processing completed. Results saved to /results/fragments/result_1.json
Worker 2: Processed 2698/4250 entries (63.48%)
Worker 3: Processed 1203/4250 entries (28.31%)
Worker 4: Processed 391/4250 entries (9.20%)
================================================================================
```

## 💾 Checkpointing & Recovery

### Automatic Checkpoints
- Creates checkpoints every 100 processed entries
- Stores in `results/fragments/checkpoints_X/` directories
- Automatically resumes from last checkpoint on restart

### Manual Recovery
If processing is interrupted:

```bash
# Restart containers - they'll automatically resume from checkpoints
docker-compose up
```

### Checkpoint Cleanup
```bash
# Remove old checkpoints to save space
find results/fragments/checkpoints_* -name "checkpoint_*.json" -mtime +7 -delete
```

## 📁 Project Structure

```
vulnerability-enhancement-pipeline/
├── README.md                    # This file
├── docker-compose.yml          # Container orchestration
├── .gitignore                  # Git ignore rules
├── master/
│   ├── Dockerfile              # Master container setup
│   └── master.py              # Coordination and monitoring logic
|   |__ backup.py               # testing file no relevance
├── worker/
│   ├── Dockerfile              # Worker container setup
│   ├── worker.py              # Processing logic
|   |__ backup.py              # testing file no relevance
|   |__ backup1.py             # testing file no relevance
│   └── start-ollama.sh        # Ollama service initialization
├── data/
│   └── vulnerability_dataset.json  # Input dataset (place here)
├── results/
    ├── vulnerability_dataset.enhanced.json  # Final outpu
    └── fragments/             # Intermediate results and checkpoints
```

## 🎯 Use Cases

### 1. Vulnerability Research
- Enhance synthetic vulnerability datasets (Juliet Test Suite)
- Improve explanation quality for security training
- Create comprehensive vulnerability databases

### 2. Machine Learning Pipeline
- Prepare high-quality training data for vulnerability detection models
- Bootstrap real-world data annotation using synthetic examples
- Create balanced datasets across different vulnerability types

### 3. Security Training
- Generate detailed explanations for security education
- Create comprehensive vulnerability examples
- Develop training materials for security professionals

## 📈 Performance

### Expected Processing Times
**These are estimates and not guarantees, performance/times highly depend on worker config, gpu power etc.**  
- **17K samples**: ~8-10 hours with 4 workers
- **Per sample**: ~4-10 seconds (depending on model size)
- **Throughput**: ~400-600 samples/hour total

### GPU Memory Usage
- **4 workers with gemma3:1b-it-qat**: ~6GB total VRAM
- **Memory per worker**: 1.5GB
- **Recommended**: Leave 1-2GB VRAM free for system stability

## 🔧 Troubleshooting

### Common Issues

#### GPU Out of Memory
```bash
# Reduce number of workers or use smaller models
# Edit docker-compose.yml:
# - Reduce NUM_WORKERS from 4 to 2
# - Use smaller model like qwen3:0.6b
```

#### Container Connection Issues
```bash
# Check Docker network
docker network ls
docker network inspect vulnerability-enhancement-pipeline_ollama-network

# Restart containers
docker-compose down
docker-compose up --build
```

#### Slow Processing
```bash
# Check GPU utilization
nvidia-smi

# Verify all workers are active
docker-compose logs --tail=20
```

### Debug Mode

Enable verbose logging:
```bash
# Set LOG_LEVEL=DEBUG in docker-compose.yml
docker-compose up --build
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Setup

```bash
# For local development without Docker
pip install -r requirements.txt
ollama pull gemma3:1b-it-qat

# Run individual components
python master/master.py
python worker/worker.py
```

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
