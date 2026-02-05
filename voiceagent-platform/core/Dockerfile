FROM python:3.12-slim

# System Dependencies fuer PJSIP
RUN apt-get update && apt-get install -y \
    build-essential \
    libasound2-dev \
    libssl-dev \
    libopus-dev \
    libspeex-dev \
    libspeexdsp-dev \
    libsndfile1-dev \
    pkg-config \
    swig \
    wget \
    && rm -rf /var/lib/apt/lists/*

# PJSIP aus Source kompilieren
WORKDIR /tmp
RUN wget -q https://github.com/pjsip/pjproject/archive/refs/tags/2.14.1.tar.gz \
    && tar xzf 2.14.1.tar.gz \
    && cd pjproject-2.14.1 \
    && ./configure --enable-shared \
        --with-opus=/usr \
        --with-speex=/usr \
        --disable-video \
        CFLAGS="-fPIC -O2" \
    && make dep && make \
    && pip install setuptools \
    && cd pjsip-apps/src/swig/python \
    && make \
    && make install \
    && cd /tmp && rm -rf pjproject-2.14.1 2.14.1.tar.gz

# Python Dependencies
WORKDIR /app
COPY core/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# App Code
COPY core/ /app/core/
COPY agents/ /app/agents/

# Data Verzeichnisse
RUN mkdir -p /app/data /app/workspace /app/config

# Environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

EXPOSE 8085

CMD ["uvicorn", "core.app.main:app", "--host", "0.0.0.0", "--port", "8085"]
