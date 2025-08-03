# Makefile pour gestion du projet d'optimisation vidéo

.PHONY: build up down logs restart clean setup dev prod

# Variables
COMPOSE_FILE = docker-compose.yml
PROJECT_NAME = video-optimizer

# Construction de l'image
build:
	docker-compose -f $(COMPOSE_FILE) build

# Démarrage des services
up:
	docker-compose -f $(COMPOSE_FILE) up -d

# Arrêt des services
down:
	docker-compose -f $(COMPOSE_FILE) down

# Affichage des logs
logs:
	docker-compose -f $(COMPOSE_FILE) logs -f

# Logs d'un service spécifique
logs-api:
	docker-compose -f $(COMPOSE_FILE) logs -f video-optimizer

# Redémarrage des services
restart:
	docker-compose -f $(COMPOSE_FILE) restart

# Nettoyage complet
clean:
	docker-compose -f $(COMPOSE_FILE) down -v --rmi all
	docker system prune -f

# Configuration initiale
setup:
	mkdir -p videos/input videos/output videos/temp logs nginx/ssl
	cp .env.example .env
	echo "Configuration initiale terminée. Éditez le fichier .env avec vos paramètres."

# Mode développement
dev:
	docker-compose -f $(COMPOSE_FILE) -f docker-compose.dev.yml up --build

# Mode production
prod:
	docker-compose -f $(COMPOSE_FILE) up -d --build

# Statut des conteneurs
status:
	docker-compose -f $(COMPOSE_FILE) ps

# Shell dans le conteneur principal
shell:
	docker-compose -f $(COMPOSE_FILE) exec video-optimizer bash

# Tests de l'API
test:
	curl -X GET http://localhost:5000/health
	curl -X GET http://localhost:5000/api/v1/status

# Nettoyage des fichiers temporaires
clean-temp:
	docker-compose -f $(COMPOSE_FILE) exec video-optimizer find /app/temp -type f -mtime +1 -delete

# Sauvegarde des logs
backup-logs:
	tar -czf backup-logs-$(shell date +%Y%m%d_%H%M%S).tar.gz logs/

# Mise à jour des images
update:
	docker-compose -f $(COMPOSE_FILE) pull
	docker-compose -f $(COMPOSE_FILE) up -d

# Aide
help:
	@echo "Commandes disponibles:"
	@echo "  build      - Construire les images Docker"
	@echo "  up         - Démarrer les services"
	@echo "  down       - Arrêter les services"
	@echo "  logs       - Afficher les logs"
	@echo "  restart    - Redémarrer les services"
	@echo "  clean      - Nettoyage complet"
	@echo "  setup      - Configuration initiale"
	@echo "  dev        - Mode développement"
	@echo "  prod       - Mode production"
	@echo "  status     - Statut des conteneurs"
	@echo "  shell      - Shell dans le conteneur"
	@echo "  test       - Test de l'API"
	@echo "  clean-temp - Nettoyage fichiers temporaires"