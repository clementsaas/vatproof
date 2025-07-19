"""
Routes d'authentification pour VATProof avec base de données
Gère l'inscription, connexion et gestion des utilisateurs
"""
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from datetime import datetime, date
import re

from app import db
from app.models.user import User, SystemLog

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Page et traitement de connexion"""
    if request.method == 'GET':
        return render_template('auth/login.html', title='Connexion - VATProof')
    
    # Traitement POST
    try:
        data = request.get_json() if request.is_json else request.form
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        if not email or not password:
            return jsonify({'error': 'Email et mot de passe requis'}), 400
        
        # Recherche de l'utilisateur
        user = User.query.filter_by(email=email).first()
        
        if not user or not user.check_password(password):
            # Log de tentative de connexion échouée
            SystemLog.log_warning('auth', f'Tentative de connexion échouée pour {email}')
            return jsonify({'error': 'Email ou mot de passe incorrect'}), 401
        
        if not user.is_active:
            SystemLog.log_warning('auth', f'Tentative de connexion sur compte désactivé: {email}')
            return jsonify({'error': 'Compte désactivé'}), 401
        
        # Connexion réussie
        session['user_id'] = str(user.id)
        session['user_email'] = user.email
        session['logged_in'] = True
        
        # Mise à jour de la dernière connexion
        user.last_login = datetime.utcnow()
        db.session.commit()
        
        # Log de connexion réussie
        SystemLog.log_info('auth', f'Connexion réussie pour {user.email}', user_id=user.id)
        
        if request.is_json:
            return jsonify({
                'success': True,
                'message': 'Connexion réussie',
                'user': user.to_dict()
            })
        else:
            flash('Connexion réussie', 'success')
            return redirect(url_for('main.home'))
            
    except Exception as e:
        SystemLog.log_error('auth', f'Erreur lors de la connexion: {str(e)}')
        return jsonify({'error': f'Erreur lors de la connexion: {str(e)}'}), 500

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Page et traitement d'inscription"""
    if request.method == 'GET':
        return render_template('auth/register.html', title='Inscription - VATProof')
    
    # Traitement POST
    try:
        data = request.get_json() if request.is_json else request.form
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        company_name = data.get('company_name', '').strip()
        
        # Validations
        if not email or not password:
            return jsonify({'error': 'Email et mot de passe requis'}), 400
        
        if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            return jsonify({'error': 'Format d\'email invalide'}), 400
        
        if len(password) < 6:
            return jsonify({'error': 'Le mot de passe doit contenir au moins 6 caractères'}), 400
        
        # Vérification que l'utilisateur n'existe pas déjà
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return jsonify({'error': 'Un compte existe déjà avec cet email'}), 409
        
        # Création du nouvel utilisateur
        new_user = User(
            email=email,
            password=password,
            company_name=company_name if company_name else None
        )
        
        # Initialisation du quota mensuel
        new_user.quota_reset_date = date.today()
        
        db.session.add(new_user)
        db.session.commit()
        
        # Connexion automatique
        session['user_id'] = str(new_user.id)
        session['user_email'] = new_user.email
        session['logged_in'] = True
        
        # Log d'inscription
        SystemLog.log_info('auth', f'Nouvelle inscription: {new_user.email}', user_id=new_user.id)
        
        if request.is_json:
            return jsonify({
                'success': True,
                'message': 'Inscription réussie',
                'user': new_user.to_dict()
            })
        else:
            flash('Inscription réussie ! Bienvenue sur VATProof.', 'success')
            return redirect(url_for('main.home'))
            
    except Exception as e:
        db.session.rollback()
        SystemLog.log_error('auth', f'Erreur lors de l\'inscription: {str(e)}')
        return jsonify({'error': f'Erreur lors de l\'inscription: {str(e)}'}), 500

@auth_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    """Déconnexion"""
    user_email = session.get('user_email')
    
    # Log de déconnexion
    if user_email:
        user = User.query.filter_by(email=user_email).first()
        if user:
            SystemLog.log_info('auth', f'Déconnexion: {user.email}', user_id=user.id)
    
    session.clear()
    
    if request.is_json:
        return jsonify({'success': True, 'message': 'Déconnexion réussie'})
    else:
        flash('Vous avez été déconnecté', 'info')
        return redirect(url_for('main.home'))

@auth_bp.route('/profile')
def profile():
    """Page de profil utilisateur"""
    user = get_current_user()
    if not user:
        return redirect(url_for('auth.login'))
    
    return render_template('auth/profile.html', 
                         title='Mon profil - VATProof',
                         user=user)

@auth_bp.route('/api/me')
def api_current_user():
    """API pour récupérer les infos de l'utilisateur connecté"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Non connecté'}), 401
    
    return jsonify(user.to_dict())

@auth_bp.route('/api/quota/check')
def api_check_quota():
    """Vérifie si l'utilisateur peut effectuer des vérifications"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Non connecté'}), 401
    
    count_requested = request.args.get('count', 1, type=int)
    can_verify = user.can_verify(count_requested)
    
    return jsonify({
        'can_verify': can_verify,
        'quota_available': user.monthly_quota - user.quota_used,
        'subscription_type': user.subscription_type,
        'message': 'Quota suffisant' if can_verify else 'Quota insuffisant - Passez en Premium'
    })

@auth_bp.route('/api/quota/use', methods=['POST'])
def api_use_quota():
    """Utilise le quota de l'utilisateur"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Non connecté'}), 401
    
    data = request.get_json()
    count = data.get('count', 1)
    
    # Vérification du quota
    if not user.can_verify(count):
        return jsonify({'error': 'Quota insuffisant'}), 403
    
    # Utilisation du quota
    user.use_quota(count)
    
    return jsonify({
        'success': True,
        'quota_used': user.quota_used,
        'quota_remaining': user.monthly_quota - user.quota_used
    })

@auth_bp.route('/api/quota/reset', methods=['POST'])
def api_reset_quota():
    """Reset du quota mensuel (pour admin ou tâche automatique)"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Non connecté'}), 401
    
    # TODO: Ajouter vérification admin ou autorisation spéciale
    
    user.reset_monthly_quota()
    
    SystemLog.log_info('auth', f'Quota reset pour {user.email}', user_id=user.id)
    
    return jsonify({
        'success': True,
        'message': 'Quota mensuel remis à zéro',
        'quota_used': user.quota_used
    })

@auth_bp.route('/api/users', methods=['GET'])
def api_list_users():
    """Liste des utilisateurs (pour admin uniquement)"""
    # TODO: Implémenter vérification admin
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Non connecté'}), 401
    
    # Pour l'instant, seul Clément peut voir cette liste
    if current_user.email != 'clement@vatproof.com':
        return jsonify({'error': 'Accès non autorisé'}), 403
    
    users = User.query.order_by(User.created_at.desc()).all()
    
    return jsonify({
        'users': [user.to_dict() for user in users],
        'total_count': len(users)
    })

@auth_bp.route('/api/users/<user_id>/toggle-active', methods=['POST'])
def api_toggle_user_active(user_id):
    """Active/désactive un utilisateur (admin uniquement)"""
    current_user = get_current_user()
    if not current_user or current_user.email != 'clement@vatproof.com':
        return jsonify({'error': 'Accès non autorisé'}), 403
    
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'Utilisateur non trouvé'}), 404
        
        user.is_active = not user.is_active
        db.session.commit()
        
        action = 'activé' if user.is_active else 'désactivé'
        SystemLog.log_info('admin', f'Utilisateur {user.email} {action} par {current_user.email}', 
                          user_id=current_user.id)
        
        return jsonify({
            'success': True,
            'message': f'Utilisateur {action}',
            'is_active': user.is_active
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# Fonctions utilitaires

def login_required(f):
    """Décorateur pour les routes nécessitant une authentification"""
    from functools import wraps
    
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            if request.is_json:
                return jsonify({'error': 'Authentification requise'}), 401
            else:
                return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def get_current_user():
    """Récupère l'utilisateur actuellement connecté"""
    if not session.get('logged_in'):
        return None
    
    user_id = session.get('user_id')
    if user_id:
        return User.query.get(user_id)
    
    return None

def admin_required(f):
    """Décorateur pour les routes nécessitant des droits admin"""
    from functools import wraps
    
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Authentification requise'}), 401
        
        # Pour l'instant, seul Clément est admin
        if user.email != 'clement@vatproof.com':
            return jsonify({'error': 'Droits administrateur requis'}), 403
        
        return f(*args, **kwargs)
    return decorated_function

# Reset quotas automatique (à appeler via cron ou tâche périodique)
@auth_bp.route('/api/admin/reset-all-quotas', methods=['POST'])
@admin_required
def api_reset_all_quotas():
    """Reset tous les quotas mensuels (1er du mois)"""
    try:
        today = date.today()
        
        # Reset seulement les comptes free dont la date de reset est dépassée
        users_to_reset = User.query.filter(
            User.subscription_type == 'free',
            User.quota_reset_date < today
        ).all()
        
        reset_count = 0
        for user in users_to_reset:
            user.reset_monthly_quota()
            reset_count += 1
        
        SystemLog.log_info('admin', f'Reset automatique quotas: {reset_count} utilisateurs')
        
        return jsonify({
            'success': True,
            'message': f'{reset_count} quotas remis à zéro',
            'reset_count': reset_count
        })
        
    except Exception as e:
        db.session.rollback()
        SystemLog.log_error('admin', f'Erreur reset quotas: {str(e)}')
        return jsonify({'error': str(e)}), 500