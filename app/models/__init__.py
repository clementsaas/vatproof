# app/models/__init__.py
"""
Modèles de base de données VATProof
"""
from .user import User, VerificationJob, VerificationBatch, SystemLog

__all__ = ['User', 'VerificationJob', 'VerificationBatch', 'SystemLog']

# app/routes/__init__.py  
"""
Routes et blueprints de l'application VATProof
"""
from .main import main_bp
from .auth import auth_bp

__all__ = ['main_bp', 'auth_bp']

# app/tasks/__init__.py
"""
Tâches Celery pour VATProof
"""
from .vies_verification import verify_single_vat, process_vat_batch

__all__ = ['verify_single_vat', 'process_vat_batch']