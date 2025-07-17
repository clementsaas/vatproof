"""
Routes d'authentification pour VATProof
Gère l'inscription, connexion et gestion des utilisateurs
"""
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import uuid
import re

# Import des modèles (quand ils seront créés)
# from app.models.user import User
# from app import db

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

# Stockage temporaire en session (à remplacer par DB)
TEMP_USERS = {}

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
        
        # Vérification de l'utilisateur (temporaire)
        user = TEMP_USERS.get(email)
        if not user or not check_password_hash(user['password_hash'], password):
            return jsonify({'error': 'Email ou mot de passe incorrect'}), 401
        
        # Connexion réussie
        session['user_id'] = user['id']
        session['user_email'] = user['email']
        session['logged_in'] = True
        
        # Mise à jour de la dernière connexion
        user['last_login'] = datetime.utcnow().isoformat()
        
        if request.is_json:
            return jsonify({
                'success': True,
                'message': 'Connexion réussie',
                'user': {
                    'id': user['id'],
                    'email': user['email'],
                    'subscription_type': user['subscription_type']
                }
            })
        else:
            flash('Connexion réussie', 'success')
            return redirect(url_for('main.home'))
            
    except Exception as e:
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
        if email in TEMP_USERS:
            return jsonify({'error': 'Un compte existe déjà avec cet email'}), 409
        
        # Création du nouvel utilisateur
        user_id = str(uuid.uuid4())
        password_hash = generate_password_hash(password)
        
        new_user = {
            'id': user_id,
            'email': email,
            'password_hash': password_hash,
            'company_name': company_name,
            'subscription_type': 'free',
            'monthly_quota': 10,
            'quota_used': 0,
            'created_at': datetime.utcnow().isoformat(),
            'last_login': None,
            'is_active': True
        }
        
        TEMP_USERS[email] = new_user
        
        # Connexion automatique
        session['user_id'] = user_id
        session['user_email'] = email
        session['logged_in'] = True
        
        if request.is_json:
            return jsonify({
                'success': True,
                'message': 'Inscription réussie',
                'user': {
                    'id': user_id,
                    'email': email,
                    'subscription_type': 'free',
                    'quota': {'monthly': 10, 'used': 0}
                }
            })
        else:
            flash('Inscription réussie ! Bienvenue sur VATProof.', 'success')
            return redirect(url_for('main.home'))
            
    except Exception as e:
        return jsonify({'error': f'Erreur lors de l\'inscription: {str(e)}'}), 500

@auth_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    """Déconnexion"""
    session.clear()
    
    if request.is_json:
        return jsonify({'success': True, 'message': 'Déconnexion réussie'})
    else:
        flash('Vous avez été déconnecté', 'info')
        return redirect(url_for('main.home'))

@auth_bp.route('/profile')
def profile():
    """Page de profil utilisateur"""
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    
    user_email = session.get('user_email')
    user = TEMP_USERS.get(user_email, {})
    
    return render_template('auth/profile.html', 
                         title='Mon profil - VATProof',
                         user=user)

@auth_bp.route('/api/me')
def api_current_user():
    """API pour récupérer les infos de l'utilisateur connecté"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Non connecté'}), 401
    
    user_email = session.get('user_email')
    user = TEMP_USERS.get(user_email)
    
    if not user:
        return jsonify({'error': 'Utilisateur non trouvé'}), 404
    
    return jsonify({
        'id': user['id'],
        'email': user['email'],
        'company_name': user.get('company_name'),
        'subscription_type': user['subscription_type'],
        'quota': {
            'monthly': user['monthly_quota'],
            'used': user['quota_used'],
            'remaining': user['monthly_quota'] - user['quota_used']
        },
        'created_at': user['created_at'],
        'last_login': user.get('last_login')
    })

@auth_bp.route('/api/quota/check')
def api_check_quota():
    """Vérifie si l'utilisateur peut effectuer des vérifications"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Non connecté'}), 401
    
    user_email = session.get('user_email')
    user = TEMP_USERS.get(user_email)
    
    if not user:
        return jsonify({'error': 'Utilisateur non trouvé'}), 404
    
    count_requested = request.args.get('count', 1, type=int)
    can_verify = user['subscription_type'] != 'free' or (user['quota_used'] + count_requested) <= user['monthly_quota']
    
    return jsonify({
        'can_verify': can_verify,
        'quota_available': user['monthly_quota'] - user['quota_used'],
        'subscription_type': user['subscription_type'],
        'message': 'Quota suffisant' if can_verify else 'Quota insuffisant - Passez en Premium'
    })

@auth_bp.route('/api/quota/use', methods=['POST'])
def api_use_quota():
    """Utilise le quota de l'utilisateur"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Non connecté'}), 401
    
    user_email = session.get('user_email')
    user = TEMP_USERS.get(user_email)
    
    if not user:
        return jsonify({'error': 'Utilisateur non trouvé'}), 404
    
    data = request.get_json()
    count = data.get('count', 1)
    
    # Vérification du quota
    if user['subscription_type'] == 'free' and (user['quota_used'] + count) > user['monthly_quota']:
        return jsonify({'error': 'Quota insuffisant'}), 403
    
    # Utilisation du quota
    user['quota_used'] += count
    
    return jsonify({
        'success': True,
        'quota_used': user['quota_used'],
        'quota_remaining': user['monthly_quota'] - user['quota_used']
    })

# Fonction utilitaire pour vérifier l'authentification
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

# Fonction utilitaire pour récupérer l'utilisateur actuel
def get_current_user():
    """Récupère l'utilisateur actuellement connecté"""
    if not session.get('logged_in'):
        return None
    
    user_email = session.get('user_email')
    return TEMP_USERS.get(user_email)