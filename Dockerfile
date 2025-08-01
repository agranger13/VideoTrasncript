# Utilisation d'une image Ubuntu comme base
FROM ubuntu:22.04

# Éviter les prompts interactifs pendant l'installation
ENV DEBIAN_FRONTEND=noninteractive

# Mise à jour des paquets et installation des dépendances système
RUN apt-get update && apt-get install -y \
    # Outils de base
    curl \
    wget \
    git \
    build-essential \
    cmake \
    pkg-config \
    yasm \
    nasm \
    python3 \
    python3-pip \
    python3-dev \
    # Dépendances pour FFmpeg et encodage vidéo
    libavcodec-dev \
    libavformat-dev \
    libavutil-dev \
    libswscale-dev \
    libswresample-dev \
    libavfilter-dev \
    libavdevice-dev \
    frei0r-plugins-dev \
    # Dépendances pour rav1e
    cargo \
    rustc \
    # Codec supplémentaires
    libx264-dev \
    libx265-dev \
    libvpx-dev \
    libfdk-aac-dev \
    libmp3lame-dev \
    libopus-dev \
    libvorbis-dev \
    # Outils utiles
    mediainfo \
    && rm -rf /var/lib/apt/lists/*

# Installation de Rust (nécessaire pour rav1e)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# Compilation et installation de rav1e
RUN git clone https://github.com/xiph/rav1e.git /tmp/rav1e && \
    cd /tmp/rav1e && \
    cargo build --release && \
    cargo install --path . && \
    cp target/release/rav1e /usr/local/bin/ && \
    rm -rf /tmp/rav1e

# Compilation de FFmpeg avec support rav1e
RUN git clone https://git.ffmpeg.org/ffmpeg.git /tmp/ffmpeg && \
    cd /tmp/ffmpeg && \
    git checkout release/7.1 && \
    ./configure \
        --enable-gpl \
        --enable-version3 \
        --enable-nonfree \
        --enable-static \
        --disable-debug \
        --disable-ffplay \
        --disable-indev=sndio \
        --disable-outdev=sndio \
        --enable-fontconfig \
        --enable-frei0r \
        --enable-gnutls \
        --enable-libaom \
        --enable-libass \
        --enable-libfdk-aac \
        --enable-libfreetype \
        --enable-libmp3lame \
        --enable-libopus \
        --enable-libvorbis \
        --enable-libvpx \
        --enable-libx264 \
        --enable-libx265 \
        --enable-librav1e \
        --pkg-config-flags="--static" && \
    make -j$(nproc) && \
    make install && \
    rm -rf /tmp/ffmpeg

# Installation des librairies Python
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

# Création du répertoire de travail
WORKDIR /app

# Création des répertoires pour les vidéos
RUN mkdir -p /app/input /app/output /app/temp

# Variables d'environnement
ENV PYTHONPATH=/app
ENV FLASK_APP=app.py
ENV FLASK_ENV=production

# Exposition du port pour l'API
EXPOSE 5000

# Script d'optimisation vidéo par défaut
# COPY optimize_video.py /app/
COPY app.py /app/

# Point d'entrée
CMD ["python3", "app.py"]