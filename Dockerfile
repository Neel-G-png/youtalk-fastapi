# Use a multi-arch base image
FROM --platform=$BUILDPLATFORM python:3.10

# Set build arguments and environment variables
ARG BUILDPLATFORM
ARG TARGETPLATFORM
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    cmake \
    libssl-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Install Rust
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

WORKDIR /code

# Copy requirements file
COPY . .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install maturin && \
    LIBSQL_EXPERIMENTAL_BUILD_FROM_SOURCE=1 pip install -r /code/requirements.txt

# Command to run the application
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
