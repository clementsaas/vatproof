"""
Routes principales de l'application VATProof
Gère les endpoints pour l'interface utilisateur et l'API
"""
from flask import Blueprint, render_template, request, jsonify, current_app, send_file
from datetime import datetime
import uuid
import os

# Import des services
from app.services.file_service import FileService
from app.services.vat_service import VATService

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def home():
    return render_template('home.html', title='VATProof - Accueil')

@main_bp.route('/about')
def about():
    return render_template('about.html', title='À propos')

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
        with current_app.app_context():
            db.session.execute('SELECT 1')
        db_status = 'ok'
    except Exception as e:
        current_app.logger.error(f"Erreur base de données: {e}")
        db_status = 'error'
    
    # Test de Redis/Celery
    try:
        # Import local pour éviter les erreurs si Celery n'est pas configuré
        import redis
        r = redis.Redis(host='localhost', port=6379, db=0)
        r.ping()
        redis_status = 'ok'
    except Exception:
        redis_status = 'error'
    
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.utcnow().isoformat(),
        'services': {
            'database': db_status,
            'redis': redis_status,
            'celery': redis_status
        },
        'version': '1.0.0-mvp'
    })

@main_bp.route('/api/upload', methods=['POST'])
def api_upload():
    """
    Endpoint pour l'upload de fichiers CSV/Excel contenant les numéros de TVA
    
    Returns:
        dict: Résultat de l'upload et ID de traitement
    """
    try:
        # Vérification de la présence du fichier
        if 'file' not in request.files:
            return jsonify({'error': 'Aucun fichier fourni'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'Aucun fichier sélectionné'}), 400
        
        # Parsing du fichier
        current_app.logger.info(f"Début parsing fichier: {file.filename}")
        
        parsed_result = FileService.parse_file(file)
        
        if not parsed_result['success']:
            return jsonify({
                'error': parsed_result['error'],
                'filename': file.filename
            }), 400
        
        # Extraction des numéros de TVA
        vat_numbers = FileService.extract_vat_numbers(parsed_result)
        
        if not vat_numbers:
            return jsonify({
                'error': 'Aucun numéro de TVA trouvé dans le fichier',
                'filename': file.filename,
                'headers': parsed_result.get('headers', [])
            }), 400
        
        # Validation des numéros de TVA
        validation_results = VATService.validate_vat_list(vat_numbers)
        
        # Génération d'un ID de job unique
        job_id = str(uuid.uuid4())
        
        # Préparation de la réponse
        response_data = {
            'success': True,
            'job_id': job_id,
            'filename': file.filename,
            'message': f'Fichier analysé avec succès',
            'stats': {
                'total_lines': parsed_result['row_count'],
                'total_vat_numbers': len(vat_numbers),
                'valid_count': validation_results['summary']['valid_count'],
                'invalid_count': validation_results['summary']['invalid_count'],
                'duplicate_count': validation_results['summary']['duplicate_count']
            },
            'preview': _format_preview_data(validation_results),
            'countries': validation_results['summary']['countries'],
            'status': 'parsed'
        }
        
        # Log du succès
        current_app.logger.info(
            f"Fichier {file.filename} parsé: {len(vat_numbers)} numéros, "
            f"{validation_results['summary']['valid_count']} valides"
        )
        
        return jsonify(response_data)
        
    except Exception as e:
        current_app.logger.error(f"Erreur lors de l'upload: {str(e)}")
        return jsonify({
            'error': 'Erreur interne lors du traitement du fichier',
            'details': str(e) if current_app.debug else None
        }), 500

@main_bp.route('/api/verify-paste', methods=['POST'])
def api_verify_paste():
    """
    Endpoint pour traiter les numéros de TVA collés directement
    
    Returns:
        dict: Résultat du parsing et ID de traitement
    """
    try:
        data = request.get_json()
        
        if not data or 'content' not in data:
            return jsonify({'error': 'Contenu manquant'}), 400
        
        content = data['content'].strip()
        if not content:
            return jsonify({'error': 'Contenu vide'}), 400
        
        current_app.logger.info("Début parsing contenu collé")
        
        # Extraction des numéros de TVA du texte
        vat_numbers = FileService.parse_text_content(content)
        
        if not vat_numbers:
            return jsonify({
                'error': 'Aucun numéro de TVA détecté dans le contenu',
                'content_preview': content[:200] + '...' if len(content) > 200 else content
            }), 400
        
        # Validation des numéros de TVA
        validation_results = VATService.validate_vat_list(vat_numbers)
        
        # Génération d'un ID de job unique
        job_id = str(uuid.uuid4())
        
        # Préparation de la réponse
        response_data = {
            'success': True,
            'job_id': job_id,
            'source': 'paste',
            'message': f'{len(vat_numbers)} numéros de TVA détectés',
            'stats': {
                'total_lines': len(content.split('\n')),
                'total_vat_numbers': len(vat_numbers),
                'valid_count': validation_results['summary']['valid_count'],
                'invalid_count': validation_results['summary']['invalid_count'],
                'duplicate_count': validation_results['summary']['duplicate_count']
            },
            'preview': _format_preview_data(validation_results),
            'countries': validation_results['summary']['countries'],
            'status': 'parsed'
        }
        
        # Log du succès
        current_app.logger.info(
            f"Contenu collé parsé: {len(vat_numbers)} numéros, "
            f"{validation_results['summary']['valid_count']} valides"
        )
        
        return jsonify(response_data)
        
    except Exception as e:
        current_app.logger.error(f"Erreur lors du parsing paste: {str(e)}")
        return jsonify({
            'error': 'Erreur interne lors du traitement du contenu',
            'details': str(e) if current_app.debug else None
        }), 500

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
    # Placeholder pour le moment - simulation d'un job en cours
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
        'estimated_completion': None,
        'message': 'Job en attente de traitement (simulation)'
    })

@main_bp.route('/api/batches/<batch_id>/download')
def api_download_batch_zip(batch_id):
    """
    Génère et télécharge le ZIP d'un lot terminé
    TODO: Implémenter avec la nouvelle architecture de base
    
    Args:
        batch_id (str): ID du lot
        
    Returns:
        File: Fichier ZIP ou erreur JSON
    """
    return jsonify({
        'error': 'Fonctionnalité en cours de développement',
        'message': 'Le téléchargement ZIP sera disponible dans la prochaine version'
    }), 501

@main_bp.route('/api/batches/<batch_id>/zip-info')
def api_batch_zip_info(batch_id):
    """
    Récupère les informations sur le ZIP d'un lot
    TODO: Implémenter avec la nouvelle architecture de base
    
    Args:
        batch_id (str): ID du lot
        
    Returns:
        dict: Informations sur le ZIP disponible
    """
    return jsonify({
        'error': 'Fonctionnalité en cours de développement',
        'message': 'Les informations ZIP seront disponibles dans la prochaine version'
    }), 501

def _format_preview_data(validation_results):
    """
    Formate les données de validation pour la prévisualisation
    
    Args:
        validation_results (dict): Résultats de VATService.validate_vat_list
        
    Returns:
        list: Données formatées pour l'affichage
    """
    preview = []
    
    # Prendre les 10 premiers résultats (valides et invalides mélangés)
    all_results = validation_results['valid'][:5] + validation_results['invalid'][:5]
    
    for result in all_results[:10]:  # Limite à 10 pour la prévisualisation
        preview_item = {
            'line_number': result.get('line_number', 0),
            'original': result['original'],
            'cleaned': result['cleaned'],
            'country_code': result.get('country_code'),
            'country_name': VATService.get_country_name(result.get('country_code', '')) if result.get('country_code') else None,
            'is_valid': result['is_valid'],
            'is_duplicate': result.get('is_duplicate', False),
            'error': result.get('error'),
            'status_class': _get_status_class(result)
        }
        preview.append(preview_item)
    
    return preview

def _get_status_class(validation_result):
    """
    Détermine la classe CSS pour le statut d'un numéro de TVA
    
    Args:
        validation_result (dict): Résultat de validation
        
    Returns:
        str: Classe CSS appropriée
    """
    if validation_result.get('is_duplicate'):
        return 'warning'  # Badge orange pour les doublons
    elif validation_result['is_valid']:
        return 'success'  # Badge vert pour les valides
    else:
        return 'danger'   # Badge rouge pour les invalides

# Gestionnaires d'erreurs
@main_bp.errorhandler(404)
def not_found_error(error):
    """Gestionnaire d'erreur 404"""
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Endpoint non trouvé'}), 404
    return render_template('errors/404.html'), 404

@main_bp.errorhandler(500)
def internal_error(error):
    """Gestionnaire d'erreur 500"""
    current_app.logger.error(f"Erreur interne: {error}")
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Erreur interne du serveur'}), 500
    return render_template('errors/500.html'), 500