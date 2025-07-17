"""
Service de stockage et suivi des jobs de vérification
Gère le stockage temporaire des jobs et leur progression
"""
import json
import time
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import redis
import uuid

class JobStorageService:
    """Service pour stocker et suivre les jobs de vérification"""
    
    def __init__(self, redis_url: str = 'redis://localhost:6379/1'):
        """
        Initialise le service de stockage
        
        Args:
            redis_url (str): URL de connexion Redis
        """
        self.redis_client = redis.from_url(redis_url)
        self.job_prefix = "vatproof:job:"
        self.batch_prefix = "vatproof:batch:"
        self.default_ttl = 86400  # 24 heures
    
    def create_batch(self, user_id: str, vat_data: List[Dict]) -> str:
        """
        Crée un nouveau lot de vérifications
        
        Args:
            user_id (str): ID de l'utilisateur
            vat_data (List[Dict]): Liste des numéros de TVA à vérifier
            
        Returns:
            str: ID du lot créé
        """
        batch_id = str(uuid.uuid4())
        
        batch_info = {
            'batch_id': batch_id,
            'user_id': user_id,
            'created_at': datetime.utcnow().isoformat(),
            'status': 'created',
            'total_jobs': len(vat_data),
            'completed_jobs': 0,
            'failed_jobs': 0,
            'vat_data': vat_data,
            'job_ids': []
        }
        
        # Stockage du lot
        self.redis_client.setex(
            f"{self.batch_prefix}{batch_id}",
            self.default_ttl,
            json.dumps(batch_info)
        )
        
        return batch_id
    
    def create_job(self, batch_id: str, country_code: str, vat_number: str, 
                   line_number: int = None, company_name: str = None) -> str:
        """
        Crée un job de vérification individuel
        
        Args:
            batch_id (str): ID du lot parent
            country_code (str): Code pays
            vat_number (str): Numéro de TVA
            line_number (int): Numéro de ligne dans le fichier
            company_name (str): Nom de l'entreprise (optionnel)
            
        Returns:
            str: ID du job créé
        """
        job_id = str(uuid.uuid4())
        
        job_info = {
            'job_id': job_id,
            'batch_id': batch_id,
            'country_code': country_code,
            'vat_number': vat_number,
            'line_number': line_number,
            'company_name': company_name,
            'created_at': datetime.utcnow().isoformat(),
            'status': 'pending',
            'celery_task_id': None,
            'result': None,
            'error': None,
            'started_at': None,
            'completed_at': None
        }
        
        # Stockage du job
        self.redis_client.setex(
            f"{self.job_prefix}{job_id}",
            self.default_ttl,
            json.dumps(job_info)
        )
        
        # Ajout du job au lot
        self._add_job_to_batch(batch_id, job_id)
        
        return job_id
    
    def update_job_status(self, job_id: str, status: str, 
                         celery_task_id: str = None, result: Dict = None, 
                         error: str = None):
        """
        Met à jour le statut d'un job
        
        Args:
            job_id (str): ID du job
            status (str): Nouveau statut
            celery_task_id (str): ID de la tâche Celery
            result (Dict): Résultat de la vérification
            error (str): Message d'erreur
        """
        job_info = self.get_job(job_id)
        if not job_info:
            return
        
        job_info['status'] = status
        
        if celery_task_id:
            job_info['celery_task_id'] = celery_task_id
        
        if status == 'processing' and not job_info.get('started_at'):
            job_info['started_at'] = datetime.utcnow().isoformat()
        
        if status in ['completed', 'failed']:
            job_info['completed_at'] = datetime.utcnow().isoformat()
            
            if result:
                job_info['result'] = result
            
            if error:
                job_info['error'] = error
        
        # Sauvegarde
        self.redis_client.setex(
            f"{self.job_prefix}{job_id}",
            self.default_ttl,
            json.dumps(job_info)
        )
        
        # Mise à jour du lot parent
        self._update_batch_progress(job_info['batch_id'])
    
    def get_job(self, job_id: str) -> Optional[Dict]:
        """
        Récupère les informations d'un job
        
        Args:
            job_id (str): ID du job
            
        Returns:
            Optional[Dict]: Informations du job ou None
        """
        data = self.redis_client.get(f"{self.job_prefix}{job_id}")
        if data:
            return json.loads(data)
        return None
    
    def get_batch(self, batch_id: str) -> Optional[Dict]:
        """
        Récupère les informations d'un lot
        
        Args:
            batch_id (str): ID du lot
            
        Returns:
            Optional[Dict]: Informations du lot ou None
        """
        data = self.redis_client.get(f"{self.batch_prefix}{batch_id}")
        if data:
            return json.loads(data)
        return None
    
    def get_batch_jobs(self, batch_id: str) -> List[Dict]:
        """
        Récupère tous les jobs d'un lot
        
        Args:
            batch_id (str): ID du lot
            
        Returns:
            List[Dict]: Liste des jobs du lot
        """
        batch_info = self.get_batch(batch_id)
        if not batch_info:
            return []
        
        jobs = []
        for job_id in batch_info.get('job_ids', []):
            job = self.get_job(job_id)
            if job:
                jobs.append(job)
        
        return jobs
    
    def get_batch_progress(self, batch_id: str) -> Dict:
        """
        Calcule la progression d'un lot
        
        Args:
            batch_id (str): ID du lot
            
        Returns:
            Dict: Statistiques de progression
        """
        jobs = self.get_batch_jobs(batch_id)
        
        total = len(jobs)
        pending = len([j for j in jobs if j['status'] == 'pending'])
        processing = len([j for j in jobs if j['status'] == 'processing'])
        completed = len([j for j in jobs if j['status'] == 'completed'])
        failed = len([j for j in jobs if j['status'] == 'failed'])
        
        percentage = 0
        if total > 0:
            percentage = int(((completed + failed) / total) * 100)
        
        return {
            'total': total,
            'pending': pending,
            'processing': processing,
            'completed': completed,
            'failed': failed,
            'percentage': percentage,
            'is_complete': (completed + failed) == total
        }
    
    def _add_job_to_batch(self, batch_id: str, job_id: str):
        """Ajoute un job à un lot"""
        batch_info = self.get_batch(batch_id)
        if batch_info:
            batch_info['job_ids'].append(job_id)
            self.redis_client.setex(
                f"{self.batch_prefix}{batch_id}",
                self.default_ttl,
                json.dumps(batch_info)
            )
    
    def _update_batch_progress(self, batch_id: str):
        """Met à jour la progression d'un lot"""
        batch_info = self.get_batch(batch_id)
        if not batch_info:
            return
        
        progress = self.get_batch_progress(batch_id)
        
        batch_info['completed_jobs'] = progress['completed']
        batch_info['failed_jobs'] = progress['failed']
        
        if progress['is_complete']:
            batch_info['status'] = 'completed'
            batch_info['completed_at'] = datetime.utcnow().isoformat()
        elif progress['processing'] > 0:
            batch_info['status'] = 'processing'
        
        self.redis_client.setex(
            f"{self.batch_prefix}{batch_id}",
            self.default_ttl,
            json.dumps(batch_info)
        )
    
    def cleanup_expired_jobs(self, max_age_hours: int = 24):
        """
        Nettoie les jobs expirés
        
        Args:
            max_age_hours (int): Âge maximum en heures
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
        
        # Recherche des clés de jobs
        job_keys = self.redis_client.keys(f"{self.job_prefix}*")
        batch_keys = self.redis_client.keys(f"{self.batch_prefix}*")
        
        cleaned_count = 0
        
        for key in job_keys + batch_keys:
            try:
                data = json.loads(self.redis_client.get(key))
                created_at = datetime.fromisoformat(data['created_at'])
                
                if created_at < cutoff_time:
                    self.redis_client.delete(key)
                    cleaned_count += 1
                    
            except:
                # En cas d'erreur, supprimer la clé corrompue
                self.redis_client.delete(key)
                cleaned_count += 1
        
        return cleaned_count