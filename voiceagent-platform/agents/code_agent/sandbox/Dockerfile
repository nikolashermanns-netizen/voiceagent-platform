FROM python:3.12-slim

# Grundlegende Tools
RUN apt-get update && apt-get install -y \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Nuetzliche Python Pakete
RUN pip install --no-cache-dir \
    numpy \
    pandas \
    matplotlib \
    requests \
    beautifulsoup4 \
    pillow

WORKDIR /workspace

# Kein Netzwerk - wird beim docker run mit --network none erzwungen
# Resource Limits werden ebenfalls beim docker run gesetzt

CMD ["python3"]
