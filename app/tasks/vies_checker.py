"""
Tâches Celery pour la vérification des numéros de TVA via VIES
Gère l'exécution asynchrone des vérifications pour éviter de bloquer Flask
"""
from celery import Celery
from datetime import datetime
import time
import logging

# Configuration du logger
logger = logging.getLogger(__name__)

# Instance Celery (sera configurée dans create_app)
celery = Celery('vatproof')

def test_celery_connection():
    """
    Test de la connexion à Celery/Redis
    
    Returns:
        str: Statut de la connexion
    """
    try:
        # Test simple de ping vers Redis
        i = celery.control.inspect()
        if i.stats():
            return 'ok'
        else:
            return 'no_workers'
    except Exception as e:
        logger.error(f"Erreur connexion Celery: {e}")
        return 'error'

@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def verify_vat_number(self, job_id, vat_number, country_code, company_name=None):
    """
    Tâche Celery pour vérifier un numéro de TVA via VIES
    
    Args:
        job_id (str): ID du job de vérification
        vat_number (str): Numéro de TVA à vérifier
        country_code (str): Code pays (FR, DE, etc.)
        company_name (str, optional): Nom de l'entreprise
        
    Returns:
        dict: Résultat de la vérification
    """
    try:
        # Import local pour éviter les imports circulaires
        from app.models.user import VerificationJob
        from app import db
        
        # Récupération du job
        job = VerificationJob.query.get(job_id)
        if not job:
            raise Exception(f"Job {job_id} non trouvé")
        
        # Marquer le job comme en cours
        job.set_processing(self.request.id)
        
        logger.info(f"Début vérification TVA {vat_number} (Job: {job_id})")
        
        # TODO: Implémenter la logique VIES ici
        # Pour l'instant, simulation d'une vérification
        result = simulate_vies_verification(vat_number, country_code)
        
        # Mise à jour du job avec le résultat
        if result['success']:
            job.set_completed(
                is_valid=result['is_valid'],
                vies_response=str(result),
                pdf_path=result.get('pdf_path')
            )
            logger.info(f"Vérification réussie pour {vat_number}")
        else:
            job.set_failed(result['error'])
            logger.error(f"Échec vérification {vat_number}: {result['error']}")
        
        return result
        
    except Exception as exc:
        logger.error(f"Erreur lors de la vérification {vat_number}: {exc}")
        
        # Marquer le job comme échoué
        try:
            job = VerificationJob.query.get(job_id)
            if job:
                job.set_failed(str(exc))
        except:
            pass
        
        # Retry en cas d'erreur temporaire
        if self.request.retries < self.max_retries:
            logger.info(f"Retry #{self.request.retries + 1} pour {vat_number}")
            raise self.retry(exc=exc)
        
        raise exc

def simulate_vies_verification(vat_number, country_code):
    """
    Simulation d'une vérification VIES (à remplacer par la vraie logique)
    
    Args:
        vat_number (str): Numéro de TVA
        country_code (str): Code pays
        
    Returns:
        dict: Résultat simulé
    """
    # Simulation d'un délai de traitement
    time.sleep(2)
    
    # Simulation de différents cas
    if vat_number.endswith('000'):
        # Numéro invalide simulé
        return {
            'success': True,
            'is_valid': False,
            'message': 'Numéro de TVA invalide',
            'verification_date': datetime.utcnow().isoformat()
        }
    elif vat_number.endswith('999'):
        # Erreur VIES simulée
        return {
            'success': False,
            'error': 'Service VIES temporairement indisponible'
        }
    else:
        # Numéro valide simulé
        return {
            'success': True,
            'is_valid': True,
            'company_name': f'Entreprise {vat_number[-4:]}',
            'company_address': f'Adresse {country_code}',
            'verification_date': datetime.utcnow().isoformat(),
            'pdf_path': f'temp_pdf/{country_code}{vat_number}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
        }

@celery.task
def process_vat_batch(batch_id, job_ids):
    """
    Traite un lot de vérifications de TVA
    
    Args:
        batch_id (str): ID du lot
        job_ids (list): Liste des IDs de jobs à traiter
        
    Returns:
        dict: Résultat du traitement du lot
    """
    try:
        from app.models.user import VerificationBatch
        from app import db
        
        logger.info(f"Début traitement lot {batch_id} avec {len(job_ids)} jobs")
        
        # Récupération du lot
        batch = VerificationBatch.query.get(batch_id)
        if not batch:
            raise Exception(f"Lot {batch_id} non trouvé")
        
        batch.status = 'processing'
        db.session.commit()
        
        # Lancement des vérifications en parallèle
        results = []
        for job_id in job_ids:
            # Récupération du job pour obtenir les paramètres
            from app.models.user import VerificationJob
            job = VerificationJob.query.get(job_id)
            if job:
                # Lancement asynchrone de la vérification
                task = verify_vat_number.delay(
                    job_id=job_id,
                    vat_number=job.vat_number,
                    country_code=job.country_code,
                    company_name=job.company_name
                )
                results.append({
                    'job_id': job_id,
                    'task_id': task.id,
                    'vat_number': job.vat_number
                })
        
        logger.info(f"Lot {batch_id}: {len(results)} vérifications lancées")
        
        return {
            'batch_id': batch_id,
            'launched_jobs': len(results),
            'results': results
        }
        
    except Exception as exc:
        logger.error(f"Erreur traitement lot {batch_id}: {exc}")
        try:
            batch = VerificationBatch.query.get(batch_id)
            if batch:
                batch.status = 'failed'
                db.session.commit()
        except:
            pass
        raise exc

@celery.task
def generate_batch_zip(batch_id):
    """
    Génère le fichier ZIP avec tous les PDF d'un lot
    
    Args:
        batch_id (str): ID du lot
        
    Returns:
        dict: Informations sur le ZIP généré
    """
    try:
        from app.models.user import VerificationBatch
        from app import db
        import os
        import zipfile
        from datetime import datetime
        
        logger.info(f"Génération ZIP pour le lot {batch_id}")
        
        # Récupération du lot
        batch = VerificationBatch.query.get(batch_id)
        if not batch:
            raise Exception(f"Lot {batch_id} non trouvé")
        
        # Vérification que tous les jobs sont terminés
        completed_jobs = batch.jobs.filter_by(status='completed', is_valid=True).all()
        
        if not completed_jobs:
            raise Exception("Aucun job terminé avec succès")
        
        # Création du nom du fichier ZIP
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"VATProof_Export_{timestamp}.zip"
        zip_path = os.path.join('temp_pdf', zip_filename)
        
        # Création du ZIP
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for job in completed_jobs:
                if job.pdf_path and os.path.exists(job.pdf_path):
                    # Nom du fichier dans le ZIP
                    pdf_name = f"{job.country_code}{job.vat_number}_{job.company_name or 'Unknown'}_{timestamp}.pdf"
                    zipf.write(job.pdf_path, pdf_name)
        
        # Mise à jour du lot
        batch.zip_filename = zip_filename
        batch.zip_path = zip_path
        batch.zip_ready = True
        db.session.commit()
        
        logger.info(f"ZIP généré: {zip_path}")
        
        return {
            'batch_id': batch_id,
            'zip_filename': zip_filename,
            'zip_path': zip_path,
            'pdf_count': len(completed_jobs)
        }
        
    except Exception as exc:
        logger.error(f"Erreur génération ZIP {batch_id}: {exc}")
        raise exc

@celery.task
def cleanup_temp_files(max_age_hours=24):
    """
    Nettoie les fichiers temporaires anciens
    
    Args:
        max_age_hours (int): Âge maximum des fichiers en heures
        
    Returns:
        dict: Statistiques de nettoyage
    """
    try:
        import os
        from datetime import datetime, timedelta
        
        logger.info(f"Nettoyage des fichiers temporaires (>{max_age_hours}h)")
        
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        cleaned_files = 0
        total_size = 0
        
        # Nettoyage du dossier temp_pdf
        temp_dir = 'temp_pdf'
        if os.path.exists(temp_dir):
            for filename in os.listdir(temp_dir):
                file_path = os.path.join(temp_dir, filename)
                if os.path.isfile(file_path):
                    file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                    if file_time < cutoff_time:
                        file_size = os.path.getsize(file_path)
                        os.remove(file_path)
                        cleaned_files += 1
                        total_size += file_size
                        logger.debug(f"Fichier supprimé: {file_path}")
        
        logger.info(f"Nettoyage terminé: {cleaned_files} fichiers, {total_size/1024/1024:.2f} MB")
        
        return {
            'cleaned_files': cleaned_files,
            'total_size_mb': total_size / 1024 / 1024,
            'max_age_hours': max_age_hours
        }
        
    except Exception as exc:
        logger.error(f"Erreur nettoyage: {exc}")
        raise exc