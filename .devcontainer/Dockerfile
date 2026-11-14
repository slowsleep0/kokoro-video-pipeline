FROM mcr.microsoft.com/devcontainers/python:3.12-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg espeak-ng fontconfig fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r /tmp/requirements.txt
RUN python -m spacy download en_core_web_sm
ENV HF_HOME=/opt/hf-cache
RUN python -c "from kokoro import KPipeline; p = KPipeline(lang_code='a'); next(p('Hello.'), None)" \
 && chmod -R a+rwX /opt/hf-cache \
 || echo "(model bake skipped)"