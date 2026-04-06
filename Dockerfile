# PMCore — Production Docker Image
# Supports NVIDIA GPU (CUDA 12.4) with CPU fallback
#
# Build:   docker build -t pmcore/pmcore:latest .
# Run:     docker run --gpus all -p 8765:8765 -v ./checkpoints:/app/checkpoints pmcore/pmcore:latest
# CPU run: docker run -p 8765:8765 -v ./checkpoints:/app/checkpoints pmcore/pmcore:latest

FROM nvidia/cuda:12.4.0-runtime-ubuntu22.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Auto-download models from HuggingFace on first start if checkpoints/ is empty
ENV PMCORE_AUTO_DOWNLOAD=1
ENV PMCORE_HF_ORG=pmcore

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3.11-dev \
    python3-pip \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Make python3.11 the default
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# Install uv for fast dependency resolution
RUN pip install uv

WORKDIR /app

# Copy dependency spec first (for layer caching)
COPY requirements.txt .

# Install Python dependencies (PyTorch with CUDA 12.4, then rest)
RUN uv pip install --system torch --index-url https://download.pytorch.org/whl/cu124 \
    && uv pip install --system -r requirements.txt

# Copy source code
COPY pmcore/ ./pmcore/
COPY api.py .
COPY scripts/ ./scripts/

# Create directories for model weights and corpus
RUN mkdir -p checkpoints corpus

# Expose FastAPI port
EXPOSE 8765

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8765/health || exit 1

# Startup: optionally auto-download models, then launch API
CMD ["sh", "-c", \
     "if [ \"$PMCORE_AUTO_DOWNLOAD\" = \"1\" ] && [ ! -f checkpoints/planner/best.pt ]; then \
         echo 'Downloading PMCore models from HuggingFace...' && \
         python scripts/download_models.py; \
      fi && \
      uvicorn api:app --host 0.0.0.0 --port 8765"]
