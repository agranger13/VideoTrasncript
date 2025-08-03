FROM linuxserver/ffmpeg:latest

# Installation des dépendances Python
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Création du répertoire de travail
WORKDIR /app

# Copie des fichiers requirements
COPY requirements.txt .

# Installation des dépendances Python
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Copie du code de l'application
COPY app.py .

# Création des répertoires pour les uploads et conversions
RUN mkdir -p /app/input /app/temp /app/output

# Variables d'environnement
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_RUN_PORT=5000

# Exposition du port
EXPOSE 5000

# Commande de démarrage
ENTRYPOINT ["python3", "app.py"]