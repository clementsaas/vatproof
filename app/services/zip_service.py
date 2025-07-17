"""
Service de génération et gestion des fichiers ZIP
Gère la création des archives avec les PDF de justification VIES
"""
import os
import zipfile
import tempfile
import shutil
from datetime import datetime
from typing import List, Dict, Optional
import uuid

class ZipService:
    """Service pour créer et gérer les archives ZIP des justificatifs"""
    
    def __init__(self, temp_dir: str = None):
        """
        Initialise le service ZIP
        
        Args:
            temp_dir (str): Répertoire temporaire pour les ZIP
        """
        self.temp_dir = temp_dir or tempfile.gettempdir()
        self.zip_prefix = "VATProof_Export_"
        self.max_zip_age_hours = 2  # Suppression auto après 2h
    
    def create_batch_zip(self, batch_id: str, completed_jobs: List[Dict]) -> Dict:
        """
        Crée un fichier ZIP avec tous les PDF d'un lot
        
        Args:
            batch_id (str): ID du lot
            completed_jobs (List[Dict]): Jobs terminés avec succès
            
        Returns:
            Dict: Informations sur le ZIP créé
        """
        try:
            # Filtrage des jobs avec PDF disponibles
            pdf_jobs = [job for job in completed_jobs 
                       if job.get('result', {}).get('pdf_path') 
                       and os.path.exists(job['result']['pdf_path'])]
            
            if not pdf_jobs:
                return {
                    'success': False,
                    'error': 'Aucun PDF disponible pour créer le ZIP'
                }
            
            # Génération du nom de fichier ZIP
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            zip_filename = f"{self.zip_prefix}{timestamp}.zip"
            zip_path = os.path.join(self.temp_dir, zip_filename)
            
            # Création du ZIP
            files_added = 0
            total_size = 0
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                
                # Ajout d'un fichier de résumé
                summary_content = self._generate_summary_content(batch_id, pdf_jobs)
                zipf.writestr("VATProof_Summary.txt", summary_content)
                
                # Ajout des PDF
                for job in pdf_jobs:
                    pdf_path = job['result']['pdf_path']
                    
                    if os.path.exists(pdf_path):
                        # Nom du fichier dans le ZIP
                        country_code = job['country_code']
                        vat_number = job['vat_number']
                        company_name = job.get('company_name', 'Unknown')
                        
                        # Nettoyage du nom de société pour le nom de fichier
                        clean_company = self._clean_filename(company_name) if company_name else 'Unknown'
                        
                        pdf_name_in_zip = f"{country_code}{vat_number}_{clean_company}_{timestamp}.pdf"
                        
                        # Ajout au ZIP
                        zipf.write(pdf_path, pdf_name_in_zip)
                        files_added += 1
                        total_size += os.path.getsize(pdf_path)
            
            # Vérification que le ZIP a été créé
            if not os.path.exists(zip_path) or files_added == 0:
                return {
                    'success': False,
                    'error': 'Erreur lors de la création du ZIP'
                }
            
            # Nettoyage des PDF originaux (optionnel)
            self._cleanup_original_pdfs(pdf_jobs)
            
            return {
                'success': True,
                'zip_path': zip_path,
                'zip_filename': zip_filename,
                'files_count': files_added,
                'total_size': total_size,
                'created_at': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Erreur lors de la création du ZIP: {str(e)}'
            }
    
    def _generate_summary_content(self, batch_id: str, pdf_jobs: List[Dict]) -> str:
        """Génère le contenu du fichier de résumé"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        content = f"""VATProof - Justificatifs de TVA intracommunautaire
================================================================

Lot de vérification: {batch_id}
Date de génération: {timestamp}
Nombre de justificatifs: {len(pdf_jobs)}

IMPORTANT:
Ces documents sont des justificatifs officiels générés par le site VIES
de la Commission européenne. Ils constituent une preuve légale de la
validité des numéros de TVA au moment de la vérification.

Conservez ces fichiers pour justifier l'autoliquidation de la TVA
en cas de contrôle fiscal.

DÉTAIL DES VÉRIFICATIONS:
========================

"""
        
        for i, job in enumerate(pdf_jobs, 1):
            result = job.get('result', {})
            country_code = job['country_code']
            vat_number = job['vat_number']
            company_name = result.get('company_name', 'N/A')
            company_address = result.get('company_address', 'N/A')
            verification_date = result.get('verification_date', 'N/A')
            
            content += f"""{i}. Numéro TVA: {country_code}{vat_number}
   Société: {company_name}
   Adresse: {company_address}
   Vérification: {verification_date}
   Statut: ✅ VALIDE

"""
        
        content += f"""
================================================================
Généré par VATProof - https://vatproof.com
Conformité: RGPD, Légal, Justificatifs officiels VIES
================================================================
"""
        
        return content
    
    def _clean_filename(self, filename: str) -> str:
        """Nettoie un nom de fichier pour le système de fichiers"""
        if not filename:
            return "Unknown"
        
        # Caractères interdits dans les noms de fichiers
        forbidden_chars = r'<>:"/\|?*'
        
        clean_name = filename
        for char in forbidden_chars:
            clean_name = clean_name.replace(char, '_')
        
        # Limitation de la longueur
        clean_name = clean_name[:50]
        
        return clean_name.strip()
    
    def _cleanup_original_pdfs(self, pdf_jobs: List[Dict]):
        """Supprime les PDF originaux après création du ZIP"""
        for job in pdf_jobs:
            try:
                pdf_path = job['result']['pdf_path']
                if os.path.exists(pdf_path):
                    os.remove(pdf_path)
            except Exception as e:
                # Log l'erreur mais continue
                print(f"Erreur suppression PDF {pdf_path}: {e}")
    
    def cleanup_old_zips(self) -> int:
        """
        Supprime les fichiers ZIP anciens
        
        Returns:
            int: Nombre de fichiers supprimés
        """
        try:
            cleaned_count = 0
            current_time = datetime.now()
            
            for filename in os.listdir(self.temp_dir):
                if filename.startswith(self.zip_prefix) and filename.endswith('.zip'):
                    file_path = os.path.join(self.temp_dir, filename)
                    
                    try:
                        # Vérification de l'âge du fichier
                        file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                        age_hours = (current_time - file_time).total_seconds() / 3600
                        
                        if age_hours > self.max_zip_age_hours:
                            os.remove(file_path)
                            cleaned_count += 1
                            
                    except Exception:
                        # En cas d'erreur, supprimer le fichier
                        try:
                            os.remove(file_path)
                            cleaned_count += 1
                        except:
                            pass
            
            return cleaned_count
            
        except Exception as e:
            print(f"Erreur nettoyage ZIP: {e}")
            return 0
    
    def get_zip_info(self, zip_path: str) -> Optional[Dict]:
        """
        Récupère les informations d'un fichier ZIP
        
        Args:
            zip_path (str): Chemin vers le fichier ZIP
            
        Returns:
            Optional[Dict]: Informations du ZIP ou None
        """
        try:
            if not os.path.exists(zip_path):
                return None
            
            with zipfile.ZipFile(zip_path, 'r') as zipf:
                file_count = len(zipf.filelist)
                total_size = sum(info.file_size for info in zipf.filelist)
                
                return {
                    'file_count': file_count,
                    'total_size': total_size,
                    'file_size': os.path.getsize(zip_path),
                    'created_at': datetime.fromtimestamp(os.path.getctime(zip_path)).isoformat()
                }
                
        except Exception:
            return None