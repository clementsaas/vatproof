"""
Configuration de l'application VATProof
Gère les paramètres d'environnement et les configurations par défaut
"""
import os
from dotenv import load_dotenv

# Chargement du fichier .env
load_dotenv()

class Config:
    """Configuration de base pour l'application Flask"""
    
    # Configuration Flask
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    FLASK_ENV = os.environ.get('FLASK_ENV') or 'development'
    
    # Configuration Base de données
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///vatproof.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = True if os.environ.get('FLASK_ENV') == 'development' else False
    
    # Configuration Redis et Celery
    REDIS_URL = os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL') or 'redis://localhost:6379/0'
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND') or 'redis://localhost:6379/0'
    
    # Configuration des uploads
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or 'temp_uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    
    # Configuration de sécurité
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None
    SESSION_COOKIE_SECURE = False  # True en production
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # Configuration VIES
    VIES_REQUEST_TIMEOUT = int(os.environ.get('VIES_REQUEST_TIMEOUT', '30'))
    VIES_DELAY_BETWEEN_REQUESTS = int(os.environ.get('VIES_DELAY_BETWEEN_REQUESTS', '5'))

class DevelopmentConfig(Config):
    """Configuration pour l'environnement de développement"""
    DEBUG = True  # Changé à True
    TESTING = False

class ProductionConfig(Config):
    """Configuration pour l'environnement de production"""
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True

class TestingConfig(Config):
    """Configuration pour les tests"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False

# Dictionnaire des configurations disponibles
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}