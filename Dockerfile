FROM nvidia/cuda:12.1.0-base-ubuntu22.04 AS base
RUN apt-get update -y \
    && apt-get install -y python3-pip  \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
RUN ldconfig /usr/local/cuda-12.1/compat/

FROM base AS pythondeps
# Install Python dependencies
COPY builder/requirements.txt /requirements.txt
COPY builder/tabbyAPI /tabbyAPI
RUN --mount=type=cache,target=/root/.cache/pip \
    python3 -m pip install --upgrade pip && \
    python3 -m pip install --upgrade -r /requirements.txt && \
    cd /tabbyAPI && python3 -m pip install '.[cu121]'

FROM pythondeps AS model
ARG MODEL_NAME=""
ARG MODEL_REVISION=""
ARG BASE_PATH="/runpod-volume"
RUN if [ -z "$MODEL_NAME" ]; then echo "ERROR: MODEL_NAME not provided."; exit 1; fi
COPY builder/"${MODEL_NAME}" "${BASE_PATH}/${MODEL_NAME}"
RUN if [ ! -f "${BASE_PATH}/${MODEL_NAME}/config.json" ]; then echo "ERROR: model was not successfully copied; did you download it to builder first?"; exit 1; fi

FROM model AS final
COPY src /src
COPY builder/config.yml /src
# Start the handler
CMD ["python3", "/src/handler.py"]
