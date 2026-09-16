# Official llama.cpp server image. The digest pin is managed automatically by
# .github/workflows/latest-llamacpp.yml, which follows the floating
# server-cuda tag and cuts a release named after the llama.cpp build number.
FROM ghcr.io/ggml-org/llama.cpp:server-cuda@sha256:5268283a8d6510d167364f19aee93e98180d8eb0cac4b7edb20af7e3edf40c17

ENV PYTHONUNBUFFERED=1

# Set up the working directory
WORKDIR /

RUN apt-get update --yes --quiet && DEBIAN_FRONTEND=noninteractive apt-get install --yes --quiet --no-install-recommends \
    software-properties-common \
    gpg-agent \
    build-essential apt-utils \
    && apt-get install --reinstall ca-certificates \
    && add-apt-repository --yes ppa:deadsnakes/ppa && apt update --yes --quiet \
    && DEBIAN_FRONTEND=noninteractive apt-get install --yes --quiet --no-install-recommends \
    python3.11 \
    python3.11-dev \
    python3.11-distutils \
    python3.11-lib2to3 \
    python3.11-gdbm \
    python3.11-tk \
    bash \
    curl && \
    ln -s /usr/bin/python3.11 /usr/bin/python && \
    curl -sS https://bootstrap.pypa.io/get-pip.py | python3.11 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /work

# Small, frequently changing layers first.
COPY src/requirements.txt /work/requirements.txt
RUN pip install -r /work/requirements.txt

# fetch_model.py must precede the (potentially huge) model layer.
COPY src/fetch_model.py /work/fetch_model.py

# Optional build-time model baking. Defaults are empty: builds without
# --build-arg produce the same model-less image as before.
ARG LLAMA_ARG_HF_REPO="bartowski/TheDrummer_Skyfall-31B-v4.2-GGUF"
ARG LLAMA_HF_QUANT="Q4_K_M"
ARG HF_TOKEN=""
RUN if [ -n "$LLAMA_ARG_HF_REPO" ]; then python /work/fetch_model.py "$LLAMA_ARG_HF_REPO" "$LLAMA_HF_QUANT"; fi

# Application code last so its changes don't invalidate the model layer.
ADD ./src /work
RUN chmod +x /work/start.sh

# Set the entrypoint
ENTRYPOINT ["/bin/sh", "-c", "/work/start.sh"]
