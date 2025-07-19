"""
Routes principales de l'application VATProof avec intégration Celery
Gère les endpoints pour l'interface utilisateur et l'API de vérification VIES
"""
from flask import Blueprint, render_template, request, jsonify, current_app, send_file
from datetime import datetime
import uuid
import os

from app import db
from app.models.user import User, VerificationJob, VerificationBatch, SystemLog
from app.services.file_service import FileService
from app.services.vat_service import VATService
from app.services.zip_service import ZipService
from app.routes.auth import get_current_user, login_required
from app.tasks.vies_verification import verify_single_vat, process_vat_batch

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def home():
    """Page d'accueil avec interface d'upload"""
    user = get_current_user()
    return render_template('home.html', 
                         title='VATProof - Accueil',
                         user=user)

@main_bp.route('/about')
def about():
    """Page à propos"""
    return render_template('about.html', title='À propos - VATProof')

@main_bp.route('/api/status')
def api_status():
    """Endpoint API pour vérifier le statut de l'application"""
    try:
        # Test de la connexion à la base de données
        db.session.execute('SELECT 1')
        db_status = 'ok'
    except Exception as e:
        current_app.logger.error(f"Erreur base de données: {e}")
        db_status = 'error'
    
    # Test de Redis/Celery
    try:
        from app.tasks.vies_verification import celery
        redis_status = 'ok' if celery.control.ping() else 'error'
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
@login_required
def api_upload():
    """Endpoint pour l'upload de fichiers CSV/Excel contenant les numéros de TVA"""
    user = get_current_user()
    
    try:
        # Vérification de la présence du fichier
        if 'file' not in request.files:
            return jsonify({'error': 'Aucun fichier fourni'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'Aucun fichier sélectionné'}), 400
        
        # Validation du fichier
        validation = FileService.validate_file(file)
        if not validation['is_valid']:
            return jsonify({'error': validation['error']}), 400
        
        # Parsing du fichier
        current_app.logger.info(f"Début parsing fichier: {file.filename} par {user.email}")
        
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
        
        # Vérification du quota utilisateur
        valid_count = validation_results['summary']['valid_count']
        if not user.can_verify(valid_count):
            return jsonify({
                'error': f'Quota insuffisant. Vous pouvez vérifier {user.monthly_quota - user.quota_used} numéros ce mois-ci.',
                'quota_needed': valid_count,
                'quota_available': user.monthly_quota - user.quota_used
            }), 403
        
        # Création du batch en base
        batch = VerificationBatch(
            user_id=user.id,
            original_filename=file.filename,
            file_type=validation['extension'],
            total_jobs=valid_count
        )
        db.session.add(batch)
        db.session.flush()  # Pour obtenir l'ID
        
        # Préparation de la réponse
        response_data = {
            'success': True,
            'batch_id': str(batch.id),
            'filename': file.filename,
            'message': f'Fichier analysé avec succès',
            'stats': validation_results['summary'],
            'preview': _format_preview_data(validation_results),
            'countries': validation_results['summary']['countries'],
            'status': 'parsed'
        }
        
        # Sauvegarde du batch
        db.session.commit()
        
        # Log du succès
        SystemLog.log_info('file_upload', 
                          f"Fichier {file.filename} parsé: {len(vat_numbers)} numéros, {valid_count} valides",
                          user_id=user.id)
        
        return jsonify(response_data)
        
    except Exception as e:
        db.session.rollback()
        SystemLog.log_error('file_upload', f'Erreur lors de l\'upload: {str(e)}', user_id=user.id)
        return jsonify({
            'error': 'Erreur interne lors du traitement du fichier',
            'details': str(e) if current_app.debug else None
        }), 500

@main_bp.route('/api/verify-paste', methods=['POST'])
@login_required
def api_verify_paste():
    """Endpoint pour traiter les numéros de TVA collés directement"""
    user = get_current_user()
    
    try:
        data = request.get_json()
        
        if not data or 'content' not in data:
            return jsonify({'error': 'Contenu manquant'}), 400
        
        content = data['content'].strip()
        if not content:
            return jsonify({'error': 'Contenu vide'}), 400
        
        current_app.logger.info(f"Début parsing contenu collé par {user.email}")
        
        # Extraction des numéros de TVA du texte
        vat_numbers = FileService.parse_text_content(content)
        
        if not vat_numbers:
            return jsonify({
                'error': 'Aucun numéro de TVA détecté dans le contenu',
                'content_preview': content[:200] + '...' if len(content) > 200 else content
            }), 400
        
        # Validation des numéros de TVA
        validation_results = VATService.validate_vat_list(vat_numbers)
        
        # Vérification du quota utilisateur
        valid_count = validation_results['summary']['valid_count']
        if not user.can_verify(valid_count):
            return jsonify({
                'error': f'Quota insuffisant. Vous pouvez vérifier {user.monthly_quota - user.quota_used} numéros ce mois-ci.',
                'quota_needed': valid_count,
                'quota_available': user.monthly_quota - user.quota_used
            }), 403
        
        # Création du batch en base
        batch = VerificationBatch(
            user_id=user.id,
            original_filename='Saisie manuelle',
            file_type='paste',
            total_jobs=valid_count
        )
        db.session.add(batch)
        db.session.flush()
        
        # Préparation de la réponse
        response_data = {
            'success': True,
            'batch_id': str(batch.id),
            'source': 'paste',
            'message': f'{len(vat_numbers)} numéros de TVA détectés',
            'stats': validation_results['summary'],
            'preview': _format_preview_data(validation_results),
            'countries': validation_results['summary']['countries'],
            'status': 'parsed'
        }
        
        db.session.commit()
        
        # Log du succès
        SystemLog.log_info('paste_import', 
                          f"Contenu collé parsé: {len(vat_numbers)} numéros, {valid_count} valides",
                          user_id=user.id)
        
        return jsonify(response_data)
        
    except Exception as e:
        db.session.rollback()
        SystemLog.log_error('paste_import', f'Erreur lors du parsing paste: {str(e)}', user_id=user.id)
        return jsonify({
            'error': 'Erreur interne lors du traitement du contenu',
            'details': str(e) if current_app.debug else None
        }), 500

@main_bp.route('/api/batches/<batch_id>/start-verification', methods=['POST'])
@login_required
def api_start_verification(batch_id):
    """Lance la vérification VIES pour un batch"""
    user = get_current_user()
    
    try:
        # Récupération du batch
        batch = VerificationBatch.query.filter_by(id=batch_id, user_id=user.id).first()
        if not batch:
            return jsonify({'error': 'Batch non trouvé'}), 404
        
        if batch.status != 'created':
            return jsonify({'error': 'Batch déjà en cours de traitement'}), 400
        
        # Re-parsing des données pour créer les jobs
        data = request.get_json()
        vat_data = data.get('vat_data', [])
        
        if not vat_data:
            return jsonify({'error': 'Aucune donnée de TVA fournie'}), 400
        
        # Vérification finale du quota
        if not user.can_verify(len(vat_data)):
            return jsonify({'error': 'Quota insuffisant'}), 403
        
        # Utilisation du quota
        user.use_quota(len(vat_data))
        
        # Création des jobs individuels
        job_ids = []
        for vat_item in vat_data:
            job = VerificationJob(
                user_id=user.id,
                batch_id=batch.id,
                country_code=vat_item['country_code'],
                vat_number=vat_item['vat_number'],
                original_input=vat_item.get('original_input'),
                line_number=vat_item.get('line_number'),
                company_name=vat_item.get('company_name')
            )
            db.session.add(job)
            db.session.flush()
            job_ids.append(str(job.id))
        
        # Mise à jour du batch
        batch.start_processing()
        db.session.commit()
        
        # Lancement des tâches Celery
        for job_id in job_ids:
            job = VerificationJob.query.get(job_id)
            
            # Lancement de la tâche Celery
            task = verify_single_vat.delay(
                country_code=job.country_code,
                vat_number=job.vat_number,
                job_data={
                    'job_id': job_id,
                    'batch_id': str(batch.id),
                    'user_id': str(user.id),
                    'line_number': job.line_number,
                    'company_name': job.company_name
                }
            )
            
            # Mise à jour du job avec l'ID de la tâche
            job.start_processing(task.id)
        
        # Log du lancement
        SystemLog.log_info('vies_verification', 
                          f"Batch {batch_id} lancé: {len(job_ids)} jobs",
                          user_id=user.id)
        
        return jsonify({
            'success': True,
            'batch_id': batch_id,
            'jobs_launched': len(job_ids),
            'status': 'processing',
            'message': f'{len(job_ids)} vérifications lancées'
        })
        
    except Exception as e:
        db.session.rollback()
        SystemLog.log_error('vies_verification', 
                           f'Erreur lancement batch {batch_id}: {str(e)}',
                           user_id=user.id)
        return jsonify({
            'error': 'Erreur lors du lancement des vérifications',
            'details': str(e) if current_app.debug else None
        }), 500

@main_bp.route('/api/batches/<batch_id>/status')
@login_required
def api_batch_status(batch_id):
    """Récupère le statut d'un batch et de ses jobs"""
    user = get_current_user()
    
    try:
        # Récupération du batch
        batch = VerificationBatch.query.filter_by(id=batch_id, user_id=user.id).first()
        if not batch:
            return jsonify({'error': 'Batch non trouvé'}), 404
        
        # Mise à jour de la progression
        batch.update_progress()
        
        # Récupération des jobs
        jobs = VerificationJob.query.filter_by(batch_id=batch.id).all()
        
        # Statistiques détaillées
        stats = {
            'total': len(jobs),
            'pending': len([j for j in jobs if j.status == 'pending']),
            'processing': len([j for j in jobs if j.status == 'processing']),
            'completed': len([j for j in jobs if j.status == 'completed']),
            'failed': len([j for j in jobs if j.status == 'failed']),
            'valid_results': len([j for j in jobs if j.status == 'completed' and j.is_valid]),
            'invalid_results': len([j for j in jobs if j.status == 'completed' and not j.is_valid])
        }
        
        # Détail des jobs (limité pour les gros batches)
        jobs_detail = []
        for job in jobs[:50]:  # Limiter à 50 pour les performances
            jobs_detail.append({
                'id': str(job.id),
                'country_code': job.country_code,
                'vat_number': job.vat_number,
                'original_input': job.original_input,
                'line_number': job.line_number,
                'status': job.status,
                'is_valid': job.is_valid,
                'vies_company_name': job.vies_company_name,
                'error_message': job.error_message,
                'created_at': job.created_at.isoformat(),
                'completed_at': job.completed_at.isoformat() if job.completed_at else None
            })
        
        response = {
            'batch': batch.to_dict(),
            'stats': stats,
            'progress_percentage': batch.get_progress_percentage(),
            'jobs': jobs_detail,
            'has_more_jobs': len(jobs) > 50
        }
        
        return jsonify(response)
        
    except Exception as e:
        SystemLog.log_error('batch_status', f'Erreur statut batch {batch_id}: {str(e)}', user_id=user.id)
        return jsonify({
            'error': 'Erreur lors de la récupération du statut',
            'details': str(e) if current_app.debug else None
        }), 500

@main_bp.route('/api/batches/<batch_id>/download')
@login_required
def api_download_batch_zip(batch_id):
    """Génère et télécharge le ZIP d'un lot terminé"""
    user = get_current_user()
    
    try:
        # Récupération du batch
        batch = VerificationBatch.query.filter_by(id=batch_id, user_id=user.id).first()
        if not batch:
            return jsonify({'error': 'Batch non trouvé'}), 404
        
        # Vérification que le batch est terminé
        if batch.status != 'completed':
            return jsonify({'error': 'Batch non terminé'}), 400
        
        # Récupération des jobs réussis avec PDF
        completed_jobs = VerificationJob.query.filter_by(
            batch_id=batch.id,
            status='completed',
            is_valid=True
        ).filter(VerificationJob.pdf_path.isnot(None)).all()
        
        if not completed_jobs:
            return jsonify({'error': 'Aucun justificatif disponible'}), 404
        
        # Génération du ZIP s'il n'existe pas déjà
        if not batch.zip_path or not os.path.exists(batch.zip_path):
            zip_service = ZipService()
            
            # Préparation des données pour le ZIP
            jobs_data = []
            for job in completed_jobs:
                jobs_data.append({
                    'result': {
                        'pdf_path': job.pdf_path,
                        'company_name': job.vies_company_name,
                        'company_address': job.vies_company_address,
                        'verification_date': job.verification_date.isoformat() if job.verification_date else None
                    },
                    'country_code': job.country_code,
                    'vat_number': job.vat_number,
                    'company_name': job.company_name
                })
            
            zip_result = zip_service.create_batch_zip(batch_id, jobs_data)
            
            if not zip_result['success']:
                return jsonify({'error': zip_result['error']}), 500
            
            # Enregistrement des infos ZIP en base
            batch.create_zip(zip_result['zip_path'], zip_result['zip_filename'])
        
        # Incrémentation du compteur de téléchargements
        batch.increment_download()
        
        # Log du téléchargement
        SystemLog.log_info('download', 
                          f"Téléchargement ZIP batch {batch_id}: {batch.zip_filename}",
                          user_id=user.id)
        
        # Envoi du fichier
        return send_file(
            batch.zip_path,
            as_attachment=True,
            download_name=batch.zip_filename,
            mimetype='application/zip'
        )
        
    except Exception as e:
        SystemLog.log_error('download', f'Erreur téléchargement ZIP {batch_id}: {str(e)}', user_id=user.id)
        return jsonify({
            'error': 'Erreur lors de la génération du ZIP',
            'details': str(e) if current_app.debug else None
        }), 500

@main_bp.route('/api/batches/<batch_id>/zip-info')
@login_required
def api_batch_zip_info(batch_id):
    """Récupère les informations sur le ZIP d'un lot"""
    user = get_current_user()
    
    try:
        # Récupération du batch
        batch = VerificationBatch.query.filter_by(id=batch_id, user_id=user.id).first()
        if not batch:
            return jsonify({'error': 'Batch non trouvé'}), 404
        
        # Comptage des PDF disponibles
        pdf_count = VerificationJob.query.filter_by(
            batch_id=batch.id,
            status='completed',
            is_valid=True
        ).filter(VerificationJob.pdf_path.isnot(None)).count()
        
        return jsonify({
            'batch_id': batch_id,
            'status': batch.status,
            'zip_available': bool(batch.zip_path and pdf_count > 0),
            'pdf_count': pdf_count,
            'zip_filename': batch.zip_filename,
            'download_count': batch.download_count,
            'zip_created_at': batch.zip_created_at.isoformat() if batch.zip_created_at else None,
            'successful_jobs': batch.successful_jobs,
            'total_jobs': batch.total_jobs
        })
        
    except Exception as e:
        SystemLog.log_error('zip_info', f'Erreur info ZIP {batch_id}: {str(e)}', user_id=user.id)
        return jsonify({
            'error': 'Erreur lors de la récupération des informations ZIP',
            'details': str(e) if current_app.debug else None
        }), 500

@main_bp.route('/dashboard')
@login_required
def dashboard():
    """Dashboard utilisateur avec historique des vérifications"""
    user = get_current_user()
    
    # Récupération des derniers batches
    recent_batches = VerificationBatch.query.filter_by(user_id=user.id)\
                                          .order_by(VerificationBatch.created_at.desc())\
                                          .limit(10).all()
    
    # Statistiques utilisateur
    total_verifications = VerificationJob.query.filter_by(user_id=user.id, status='completed').count()
    valid_verifications = VerificationJob.query.filter_by(user_id=user.id, status='completed', is_valid=True).count()
    
    return render_template('dashboard.html',
                         title='Dashboard - VATProof',
                         user=user,
                         recent_batches=recent_batches,
                         total_verifications=total_verifications,
                         valid_verifications=valid_verifications)

# Fonctions utilitaires

def _format_preview_data(validation_results):
    """Formate les données de validation pour la prévisualisation"""
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
    """Détermine la classe CSS pour le statut d'un numéro de TVA"""
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
    SystemLog.log_error('server', f"Erreur interne: {error}")
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Erreur interne du serveur'}), 500
    return render_template('errors/500.html'), 500