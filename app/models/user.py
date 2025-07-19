"""
Modèles de base de données pour VATProof
Définit les tables et relations pour la gestion des utilisateurs et vérifications
"""
from datetime import datetime
import uuid
from sqlalchemy.dialects.postgresql import UUID
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

from app import db

class User(db.Model):
    """Modèle utilisateur pour l'authentification et la gestion des quotas"""
    
    __tablename__ = 'users'
    
    # Clé primaire
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Authentification
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    
    # Informations profil
    company_name = db.Column(db.String(255), nullable=True)
    
    # Abonnement et quotas
    subscription_type = db.Column(db.String(50), nullable=False, default='free')
    monthly_quota = db.Column(db.Integer, nullable=False, default=10)
    quota_used = db.Column(db.Integer, nullable=False, default=0)
    quota_reset_date = db.Column(db.Date, nullable=True)
    
    # Métadonnées
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    
    # Relations
    verifications = db.relationship('VerificationJob', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    
    def __init__(self, email, password, company_name=None):
        self.email = email.lower().strip()
        self.set_password(password)
        self.company_name = company_name
        
    def set_password(self, password):
        """Hash et stocke le mot de passe"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Vérifie le mot de passe"""
        return check_password_hash(self.password_hash, password)
    
    def can_verify(self, count=1):
        """Vérifie si l'utilisateur peut effectuer des vérifications"""
        if self.subscription_type != 'free':
            return True
        return (self.quota_used + count) <= self.monthly_quota
    
    def use_quota(self, count=1):
        """Utilise le quota de l'utilisateur"""
        if self.subscription_type == 'free':
            self.quota_used += count
            db.session.commit()
    
    def reset_monthly_quota(self):
        """Remet à zéro le quota mensuel"""
        self.quota_used = 0
        self.quota_reset_date = datetime.utcnow().date()
        db.session.commit()
    
    def to_dict(self):
        """Conversion en dictionnaire pour les API"""
        return {
            'id': str(self.id),
            'email': self.email,
            'company_name': self.company_name,
            'subscription_type': self.subscription_type,
            'quota': {
                'monthly': self.monthly_quota,
                'used': self.quota_used,
                'remaining': self.monthly_quota - self.quota_used
            },
            'created_at': self.created_at.isoformat(),
            'last_login': self.last_login.isoformat() if self.last_login else None
        }
    
    def __repr__(self):
        return f'<User {self.email}>'

class VerificationJob(db.Model):
    """Modèle pour les jobs de vérification TVA individuels"""
    
    __tablename__ = 'verification_jobs'
    
    # Clé primaire
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Relations
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False, index=True)
    batch_id = db.Column(UUID(as_uuid=True), db.ForeignKey('verification_batches.id'), nullable=True, index=True)
    
    # Données TVA
    country_code = db.Column(db.String(2), nullable=False)
    vat_number = db.Column(db.String(50), nullable=False)
    original_input = db.Column(db.String(100), nullable=True)  # Saisie originale
    company_name = db.Column(db.String(255), nullable=True)
    line_number = db.Column(db.Integer, nullable=True)  # Position dans le fichier
    
    # État du job
    status = db.Column(db.String(50), nullable=False, default='pending')  # pending, processing, completed, failed
    celery_task_id = db.Column(db.String(100), nullable=True, index=True)
    
    # Résultats VIES
    is_valid = db.Column(db.Boolean, nullable=True)
    vies_company_name = db.Column(db.String(255), nullable=True)
    vies_company_address = db.Column(db.Text, nullable=True)
    verification_date = db.Column(db.DateTime, nullable=True)
    
    # Fichiers
    pdf_filename = db.Column(db.String(255), nullable=True)
    pdf_path = db.Column(db.String(500), nullable=True)  # Chemin temporaire
    
    # Logs et erreurs
    error_message = db.Column(db.Text, nullable=True)
    vies_response = db.Column(db.Text, nullable=True)  # Réponse brute VIES
    
    # Métadonnées
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    # Index pour les requêtes fréquentes
    __table_args__ = (
        db.Index('idx_user_status', 'user_id', 'status'),
        db.Index('idx_batch_status', 'batch_id', 'status'),
        db.Index('idx_vat_lookup', 'country_code', 'vat_number'),
    )
    
    def start_processing(self, celery_task_id=None):
        """Marque le job comme en cours de traitement"""
        self.status = 'processing'
        self.started_at = datetime.utcnow()
        if celery_task_id:
            self.celery_task_id = celery_task_id
        db.session.commit()
    
    def complete_success(self, vies_data):
        """Marque le job comme réussi avec les données VIES"""
        self.status = 'completed'
        self.completed_at = datetime.utcnow()
        self.is_valid = vies_data.get('is_valid', False)
        self.vies_company_name = vies_data.get('company_name')
        self.vies_company_address = vies_data.get('company_address')
        self.verification_date = datetime.utcnow()
        self.pdf_path = vies_data.get('pdf_path')
        self.vies_response = vies_data.get('vies_response')
        
        # Génération du nom de fichier PDF
        if self.pdf_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.pdf_filename = f"{self.country_code}{self.vat_number}_{timestamp}.pdf"
        
        db.session.commit()
    
    def complete_failure(self, error_message):
        """Marque le job comme échoué"""
        self.status = 'failed'
        self.completed_at = datetime.utcnow()
        self.is_valid = False
        self.error_message = error_message
        db.session.commit()
    
    def to_dict(self):
        """Conversion en dictionnaire pour les API"""
        return {
            'id': str(self.id),
            'batch_id': str(self.batch_id) if self.batch_id else None,
            'country_code': self.country_code,
            'vat_number': self.vat_number,
            'original_input': self.original_input,
            'company_name': self.company_name,
            'line_number': self.line_number,
            'status': self.status,
            'is_valid': self.is_valid,
            'vies_company_name': self.vies_company_name,
            'vies_company_address': self.vies_company_address,
            'verification_date': self.verification_date.isoformat() if self.verification_date else None,
            'pdf_filename': self.pdf_filename,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat(),
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }
    
    def __repr__(self):
        return f'<VerificationJob {self.country_code}{self.vat_number}>'

class VerificationBatch(db.Model):
    """Modèle pour les lots de vérifications (upload de fichier)"""
    
    __tablename__ = 'verification_batches'
    
    # Clé primaire
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Relations
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False, index=True)
    
    # Métadonnées du fichier
    original_filename = db.Column(db.String(255), nullable=True)
    file_type = db.Column(db.String(20), nullable=True)  # csv, xlsx, paste
    total_jobs = db.Column(db.Integer, nullable=False, default=0)
    
    # État du batch
    status = db.Column(db.String(50), nullable=False, default='created')  # created, processing, completed, failed
    
    # Statistiques
    completed_jobs = db.Column(db.Integer, nullable=False, default=0)
    successful_jobs = db.Column(db.Integer, nullable=False, default=0)
    failed_jobs = db.Column(db.Integer, nullable=False, default=0)
    
    # ZIP et téléchargement
    zip_filename = db.Column(db.String(255), nullable=True)
    zip_path = db.Column(db.String(500), nullable=True)
    zip_created_at = db.Column(db.DateTime, nullable=True)
    download_count = db.Column(db.Integer, nullable=False, default=0)
    
    # Métadonnées
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    # Relations
    jobs = db.relationship('VerificationJob', backref='batch', lazy='dynamic', cascade='all, delete-orphan')
    
    def start_processing(self):
        """Marque le batch comme en cours de traitement"""
        self.status = 'processing'
        self.started_at = datetime.utcnow()
        db.session.commit()
    
    def update_progress(self):
        """Met à jour les statistiques de progression"""
        jobs = self.jobs.all()
        self.total_jobs = len(jobs)
        self.completed_jobs = len([j for j in jobs if j.status in ['completed', 'failed']])
        self.successful_jobs = len([j for j in jobs if j.status == 'completed' and j.is_valid])
        self.failed_jobs = len([j for j in jobs if j.status == 'failed'])
        
        # Mise à jour du statut du batch
        if self.completed_jobs == self.total_jobs and self.total_jobs > 0:
            self.status = 'completed'
            self.completed_at = datetime.utcnow()
        elif self.completed_jobs > 0:
            self.status = 'processing'
        
        db.session.commit()
    
    def create_zip(self, zip_path, zip_filename):
        """Enregistre les informations du ZIP créé"""
        self.zip_path = zip_path
        self.zip_filename = zip_filename
        self.zip_created_at = datetime.utcnow()
        db.session.commit()
    
    def increment_download(self):
        """Incrémente le compteur de téléchargements"""
        self.download_count += 1
        db.session.commit()
    
    def get_progress_percentage(self):
        """Calcule le pourcentage de progression"""
        if self.total_jobs == 0:
            return 0
        return int((self.completed_jobs / self.total_jobs) * 100)
    
    def to_dict(self):
        """Conversion en dictionnaire pour les API"""
        return {
            'id': str(self.id),
            'original_filename': self.original_filename,
            'file_type': self.file_type,
            'status': self.status,
            'total_jobs': self.total_jobs,
            'completed_jobs': self.completed_jobs,
            'successful_jobs': self.successful_jobs,
            'failed_jobs': self.failed_jobs,
            'progress_percentage': self.get_progress_percentage(),
            'zip_available': bool(self.zip_path),
            'zip_filename': self.zip_filename,
            'download_count': self.download_count,
            'created_at': self.created_at.isoformat(),
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }
    
    def __repr__(self):
        return f'<VerificationBatch {self.original_filename}>'

class SystemLog(db.Model):
    """Modèle pour les logs système et monitoring"""
    
    __tablename__ = 'system_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Classification
    level = db.Column(db.String(20), nullable=False, index=True)  # INFO, WARNING, ERROR, CRITICAL
    category = db.Column(db.String(50), nullable=False, index=True)  # auth, vies, file_upload, etc.
    
    # Contenu
    message = db.Column(db.Text, nullable=False)
    details = db.Column(db.Text, nullable=True)  # JSON ou texte détaillé
    
    # Contexte
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=True, index=True)
    ip_address = db.Column(db.String(45), nullable=True)  # Support IPv6
    user_agent = db.Column(db.String(500), nullable=True)
    
    # Métadonnées
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    @classmethod
    def log_info(cls, category, message, details=None, user_id=None):
        """Log d'information"""
        cls._create_log('INFO', category, message, details, user_id)
    
    @classmethod
    def log_warning(cls, category, message, details=None, user_id=None):
        """Log d'avertissement"""
        cls._create_log('WARNING', category, message, details, user_id)
    
    @classmethod
    def log_error(cls, category, message, details=None, user_id=None):
        """Log d'erreur"""
        cls._create_log('ERROR', category, message, details, user_id)
    
    @classmethod
    def _create_log(cls, level, category, message, details, user_id):
        """Crée un log en base"""
        try:
            log = cls(
                level=level,
                category=category,
                message=message,
                details=details,
                user_id=user_id
            )
            db.session.add(log)
            db.session.commit()
        except Exception:
            # En cas d'erreur lors du logging, ne pas planter l'application
            db.session.rollback()
    
    def __repr__(self):
        return f'<SystemLog {self.level} {self.category}>'