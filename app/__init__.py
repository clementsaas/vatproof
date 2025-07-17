"""
Factory pattern pour créer l'application Flask VATProof
Initialise tous les composants : DB, Celery, routes, etc.
"""
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from celery import Celery

# Instances globales des extensions
db = SQLAlchemy()
celery = Celery(__name__)

# Export de create_app pour l'import direct
__all__ = ['create_app', 'db', 'celery']

def create_app(config_name=None):
    """
    Factory function pour créer l'application Flask
    
    Args:
        config_name (str): Nom de la configuration à utiliser
        
    Returns:
        Flask: Instance de l'application configurée
    """
    # Import local pour éviter les imports circulaires
    from config import config
    
    if config_name is None:
        config_name = os.environ.get('FLASK_CONFIG', 'default')
    
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # Initialisation des extensions
    init_extensions(app)
    
    # Enregistrement des blueprints/routes
    register_blueprints(app)
    
    # Configuration de Celery
    configure_celery(app)
    
    # Création des dossiers nécessaires
    create_directories(app)
    
    return app

def init_extensions(app):
    """Initialise toutes les extensions Flask"""
    db.init_app(app)
    
    # Création des tables en mode développement
    with app.app_context():
        db.create_all()

def register_blueprints(app):
    """Enregistre toutes les routes de l'application"""
    from app.routes import main_bp
    app.register_blueprint(main_bp)

def configure_celery(app):
    """Configure Celery pour les tâches asynchrones"""
    celery.conf.update(
        broker_url=app.config['CELERY_BROKER_URL'],
        result_backend=app.config['CELERY_RESULT_BACKEND'],
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='Europe/Paris',
        enable_utc=True,
        task_track_started=True,
        task_routes={
            'app.tasks.vies_verification.*': {'queue': 'vies_verification'}
        },
        # Configuration pour la production
        worker_prefetch_multiplier=1,
        task_acks_late=True,
        worker_max_tasks_per_child=50,
        # Délais et timeouts
        task_soft_time_limit=300,  # 5 minutes
        task_time_limit=600,       # 10 minutes
        worker_disable_rate_limits=False
    )
    
    # Mise à jour du contexte de l'app dans Celery
    class ContextTask(celery.Task):
        """Make celery tasks work with Flask app context."""
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    
    celery.Task = ContextTask

def create_directories(app):
    """Crée les dossiers nécessaires s'ils n'existent pas"""
    directories = [
        app.config['UPLOAD_FOLDER'],
        'temp_pdf',
        'logs'
    ]
    
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)

def make_celery(app):
    """
    Fonction utilitaire pour créer une instance Celery configurée avec Flask
    Utilisée pour lancer les workers
    """
    celery_instance = Celery(
        app.import_name,
        backend=app.config['CELERY_RESULT_BACKEND'],
        broker=app.config['CELERY_BROKER_URL']
    )
    
    celery_instance.conf.update(app.config)
    
    class ContextTask(celery_instance.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    
    celery_instance.Task = ContextTask
    return celery_instance