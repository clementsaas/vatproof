"""
Worker Celery pour VATProof
Lance les workers qui traitent les tâches de vérification VIES
"""
import os
import sys

# Ajout du dossier racine au PATH Python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, make_celery

# Création de l'app Flask
flask_app = create_app()

# Création de l'instance Celery
celery = make_celery(flask_app)

# Import des tâches pour les enregistrer
from app.tasks.vies_verification import verify_single_vat, process_vat_batch

if __name__ == '__main__':
    # Lancement du worker
    # Usage: python worker.py worker --loglevel=info
    celery.start()