"""
Routes principales de l'application VATProof
Gère les endpoints pour l'interface utilisateur et l'API
"""
from flask import Blueprint, render_template, request, jsonify, current_app
from datetime import datetime
import os

# Création du blueprint principal
main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def home():
    """
    Page d'accueil - Interface principale pour l'import des numéros de TVA
    
    Returns:
        str: Template HTML rendu
    """
    return render_template('home.html', 
                         title='VATProof - Vérification de TVA intracommunautaire')

@main_bp.route('/about')
def about():
    """
    Page à propos - Informations sur la plateforme et la conformité légale
    
    Returns:
        str: Template HTML rendu
    """
    return render_template('about.html', 
                         title='À propos - VATProof')

@main_bp.route('/api/status')
def api_status():
    """
    Endpoint API pour vérifier le statut de l'application
    
    Returns:
        dict: Statut de l'application et des services
    """
    try:
        # Test de la connexion à la base de données
        from app import db
        db.session.execute('SELECT 1')
        db_status = 'ok'
    except Exception as e:
        current_app.logger.error(f"Erreur base de données: {e}")
        db_status = 'error'
    
    # Test de la connexion à Redis (Celery) - optionnel pour le moment
    celery_status = 'not_configured'
    
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.utcnow().isoformat(),
        'services': {
            'database': db_status,
            'celery': celery_status
        },
        'version': '1.0.0-mvp'
    })

@main_bp.route('/api/upload', methods=['POST'])
def api_upload():
    """
    Endpoint pour l'upload de fichiers CSV/Excel contenant les numéros de TVA
    TODO: Implémenter le parsing et la validation des fichiers
    
    Returns:
        dict: Résultat de l'upload et ID de traitement
    """
    if 'file' not in request.files:
        return jsonify({'error': 'Aucun fichier fourni'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Aucun fichier sélectionné'}), 400
    
    # Validation de l'extension
    allowed_extensions = {'.csv', '.xlsx', '.xls', '.txt'}
    file_ext = os.path.splitext(file.filename)[1].lower()
    
    if file_ext not in allowed_extensions:
        return jsonify({
            'error': f'Format de fichier non supporté. Extensions autorisées: {", ".join(allowed_extensions)}'
        }), 400
    
    # Pour l'instant, on retourne juste un placeholder
    # TODO: Implémenter le parsing des fichiers et l'ajout en queue
    file_content = file.read()
    file.seek(0)  # Reset pour usage ultérieur
    
    return jsonify({
        'message': 'Fichier reçu avec succès',
        'filename': file.filename,
        'size': len(file_content),
        'job_id': 'placeholder-job-id',
        'status': 'uploaded',
        'lines_count': 10,  # Simulation
        'preview': ['FR12345678901', 'DE987654321', 'IT12312312345']  # Simulation
    })

@main_bp.route('/api/verify-paste', methods=['POST'])
def api_verify_paste():
    """
    Endpoint pour traiter les numéros de TVA collés directement
    TODO: Implémenter le parsing et la validation du texte collé
    
    Returns:
        dict: Résultat du parsing et ID de traitement
    """
    data = request.get_json()
    
    if not data or 'content' not in data:
        return jsonify({'error': 'Contenu manquant'}), 400
    
    content = data['content'].strip()
    if not content:
        return jsonify({'error': 'Contenu vide'}), 400
    
    # TODO: Parser le contenu, extraire les numéros de TVA, valider le format
    lines = [line.strip() for line in content.split('\n') if line.strip()]
    
    return jsonify({
        'message': f'{len(lines)} lignes détectées',
        'lines_count': len(lines),
        'preview': lines[:5],  # Aperçu des 5 premières lignes
        'job_id': 'placeholder-paste-job-id',
        'status': 'parsed'
    })

@main_bp.route('/api/jobs/<job_id>/status')
def api_job_status(job_id):
    """
    Endpoint pour suivre le statut d'un job de vérification
    TODO: Implémenter le suivi via Celery
    
    Args:
        job_id (str): Identifiant du job
        
    Returns:
        dict: Statut du job et progression
    """
    # Placeholder pour le moment
    return jsonify({
        'job_id': job_id,
        'status': 'pending',
        'progress': {
            'total': 0,
            'completed': 0,
            'failed': 0,
            'in_progress': 0
        },
        'created_at': datetime.utcnow().isoformat(),
        'estimated_completion': None
    })

@main_bp.errorhandler(404)
def not_found_error(error):
    """Gestionnaire d'erreur 404"""
    return render_template('errors/404.html'), 404

@main_bp.errorhandler(500)
def internal_error(error):
    """Gestionnaire d'erreur 500"""
    current_app.logger.error(f"Erreur interne: {error}")
    return render_template('errors/500.html'), 500