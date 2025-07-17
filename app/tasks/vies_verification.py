"""
Tâches Celery pour la vérification des numéros de TVA via VIES
Utilise Selenium pour automatiser le site officiel VIES
"""
import os
import time
import random
import tempfile
from datetime import datetime
from typing import Dict, Optional

from celery import Celery
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

import logging

# Configuration du logger
logger = logging.getLogger(__name__)

# Instance Celery (sera configurée dans create_app)
celery = Celery('vatproof')

class VIESAutomation:
    """Classe pour l'automatisation du site VIES"""
    
    VIES_URL = "https://ec.europa.eu/taxation_customs/vies/"
    
    def __init__(self, headless=True, delay_range=(3, 8)):
        """
        Initialise l'automatisation VIES
        
        Args:
            headless (bool): Mode headless pour Chrome
            delay_range (tuple): Délai aléatoire entre actions (min, max) en secondes
        """
        self.headless = headless
        self.delay_range = delay_range
        self.driver = None
        self.download_dir = None
        
    def setup_driver(self):
        """Configure et initialise le driver Chrome"""
        try:
            # Configuration Chrome
            chrome_options = Options()
            
            if self.headless:
                chrome_options.add_argument('--headless')
            
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            # User-Agent réaliste
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            # Configuration des téléchargements
            self.download_dir = tempfile.mkdtemp()
            prefs = {
                "download.default_directory": self.download_dir,
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True,
                "plugins.always_open_pdf_externally": True
            }
            chrome_options.add_experimental_option("prefs", prefs)
            
            # Installation automatique du driver
            service = Service(ChromeDriverManager().install())
            
            # Initialisation du driver
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            
            # Masquer l'automatisation
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            logger.info("Driver Chrome initialisé avec succès")
            return True
            
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation du driver: {e}")
            return False
    
    def human_delay(self, min_delay=None, max_delay=None):
        """Simule un délai humain"""
        if min_delay is None:
            min_delay = self.delay_range[0]
        if max_delay is None:
            max_delay = self.delay_range[1]
        
        delay = random.uniform(min_delay, max_delay)
        time.sleep(delay)
        logger.debug(f"Délai humain: {delay:.2f}s")
    
    def verify_vat_number(self, country_code: str, vat_number: str) -> Dict:
        """
        Vérifie un numéro de TVA sur le site VIES
        
        Args:
            country_code (str): Code pays (ex: 'FR', 'DE')
            vat_number (str): Numéro de TVA sans le code pays
            
        Returns:
            Dict: Résultat de la vérification
        """
        result = {
            'success': False,
            'is_valid': False,
            'company_name': None,
            'company_address': None,
            'verification_date': datetime.utcnow().isoformat(),
            'pdf_path': None,
            'error': None,
            'vies_response': None
        }
        
        try:
            if not self.driver:
                if not self.setup_driver():
                    result['error'] = 'Impossible d\'initialiser le navigateur'
                    return result
            
            logger.info(f"Début vérification: {country_code}{vat_number}")
            
            # Accès au site VIES
            self.driver.get(self.VIES_URL)
            self.human_delay(2, 4)
            
            # Gestion des cookies si nécessaire
            self._handle_cookies_banner()
            
            # Sélection du pays
            country_select = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.NAME, "memberStateCode"))
            )
            
            select = Select(country_select)
            select.select_by_value(country_code)
            self.human_delay(1, 2)
            
            # Saisie du numéro de TVA
            vat_input = self.driver.find_element(By.NAME, "number")
            vat_input.clear()
            # Simulation de frappe humaine
            for char in vat_number:
                vat_input.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15))
            
            self.human_delay(1, 3)
            
            # Soumission du formulaire
            verify_button = self.driver.find_element(By.CSS_SELECTOR, "input[type='submit'][value*='Verify']")
            verify_button.click()
            
            # Attente du résultat
            WebDriverWait(self.driver, 15).until(
                lambda driver: driver.find_elements(By.CSS_SELECTOR, ".validStyle, .invalidStyle") or
                              driver.find_elements(By.XPATH, "//*[contains(text(), 'Valid') or contains(text(), 'Invalid')]")
            )
            
            self.human_delay(2, 4)
            
            # Analyse du résultat
            result_info = self._parse_vies_result()
            result.update(result_info)
            
            # Si le numéro est valide, télécharger le PDF
            if result['is_valid']:
                pdf_path = self._download_pdf(country_code, vat_number)
                result['pdf_path'] = pdf_path
            
            result['success'] = True
            logger.info(f"Vérification réussie: {country_code}{vat_number} - Valide: {result['is_valid']}")
            
        except TimeoutException:
            result['error'] = 'Timeout lors de la vérification VIES'
            logger.error(f"Timeout pour {country_code}{vat_number}")
            
        except Exception as e:
            result['error'] = f'Erreur lors de la vérification: {str(e)}'
            logger.error(f"Erreur vérification {country_code}{vat_number}: {e}")
        
        return result
    
    def _handle_cookies_banner(self):
        """Gère la bannière de cookies si elle apparaît"""
        try:
            # Recherche de boutons de cookies courants
            cookie_selectors = [
                "button[id*='cookie'][id*='accept']",
                "button[class*='cookie'][class*='accept']",
                ".cookie-accept",
                "#cookie-accept",
                "button:contains('Accept')",
                "button:contains('Accepter')"
            ]
            
            for selector in cookie_selectors:
                try:
                    cookie_button = WebDriverWait(self.driver, 2).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    cookie_button.click()
                    logger.info("Bannière de cookies acceptée")
                    self.human_delay(1, 2)
                    return
                except:
                    continue
                    
        except Exception:
            # Pas de bannière de cookies, on continue
            pass
    
    def _parse_vies_result(self) -> Dict:
        """Parse le résultat affiché par VIES"""
        try:
            # Recherche d'éléments indiquant la validité
            page_source = self.driver.page_source.lower()
            
            if 'yes, valid vat number' in page_source or 'validstyle' in page_source:
                # Numéro valide
                company_info = self._extract_company_info()
                return {
                    'is_valid': True,
                    'company_name': company_info.get('name'),
                    'company_address': company_info.get('address'),
                    'vies_response': self.driver.page_source
                }
            elif 'no, invalid vat number' in page_source or 'invalidstyle' in page_source:
                # Numéro invalide
                return {
                    'is_valid': False,
                    'vies_response': self.driver.page_source
                }
            else:
                # Résultat ambigu
                return {
                    'is_valid': False,
                    'error': 'Résultat VIES ambigu ou service indisponible'
                }
                
        except Exception as e:
            logger.error(f"Erreur lors du parsing du résultat: {e}")
            return {
                'is_valid': False,
                'error': f'Erreur parsing résultat: {str(e)}'
            }
    
    def _extract_company_info(self) -> Dict:
        """Extrait les informations de l'entreprise depuis la page VIES"""
        try:
            company_info = {'name': None, 'address': None}
            
            # Recherche du nom de l'entreprise
            name_selectors = [
                "//td[contains(text(), 'Name')]/following-sibling::td",
                "//th[contains(text(), 'Name')]/following-sibling::td",
                ".company-name",
                "#company-name"
            ]
            
            for selector in name_selectors:
                try:
                    if selector.startswith('//'):
                        element = self.driver.find_element(By.XPATH, selector)
                    else:
                        element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    
                    company_info['name'] = element.text.strip()
                    break
                except:
                    continue
            
            # Recherche de l'adresse
            address_selectors = [
                "//td[contains(text(), 'Address')]/following-sibling::td",
                "//th[contains(text(), 'Address')]/following-sibling::td",
                ".company-address",
                "#company-address"
            ]
            
            for selector in address_selectors:
                try:
                    if selector.startswith('//'):
                        element = self.driver.find_element(By.XPATH, selector)
                    else:
                        element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    
                    company_info['address'] = element.text.strip()
                    break
                except:
                    continue
            
            return company_info
            
        except Exception as e:
            logger.error(f"Erreur extraction info entreprise: {e}")
            return {'name': None, 'address': None}
    
    def _download_pdf(self, country_code: str, vat_number: str) -> Optional[str]:
        """Télécharge le PDF de justification depuis VIES"""
        try:
            # Recherche du bouton/lien d'impression
            print_selectors = [
                "input[value*='Print']",
                "a[href*='print']",
                "button:contains('Print')",
                ".print-button"
            ]
            
            for selector in print_selectors:
                try:
                    print_element = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    
                    # Clic sur imprimer
                    print_element.click()
                    self.human_delay(2, 4)
                    
                    # Attente du téléchargement
                    pdf_path = self._wait_for_download(country_code, vat_number)
                    return pdf_path
                    
                except:
                    continue
            
            # Si pas de bouton d'impression trouvé, essayer Ctrl+P
            self.driver.execute_script("window.print();")
            self.human_delay(3, 5)
            
            return self._wait_for_download(country_code, vat_number)
            
        except Exception as e:
            logger.error(f"Erreur téléchargement PDF: {e}")
            return None
    
    def _wait_for_download(self, country_code: str, vat_number: str, timeout: int = 30) -> Optional[str]:
        """Attend qu'un fichier soit téléchargé et le renomme"""
        try:
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                files = os.listdir(self.download_dir)
                
                # Recherche de fichiers PDF
                pdf_files = [f for f in files if f.endswith('.pdf') and not f.endswith('.crdownload')]
                
                if pdf_files:
                    # Prendre le plus récent
                    pdf_file = max(pdf_files, key=lambda f: os.path.getctime(os.path.join(self.download_dir, f)))
                    old_path = os.path.join(self.download_dir, pdf_file)
                    
                    # Nouveau nom avec timestamp
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    new_filename = f"{country_code}{vat_number}_{timestamp}.pdf"
                    new_path = os.path.join(self.download_dir, new_filename)
                    
                    os.rename(old_path, new_path)
                    logger.info(f"PDF téléchargé: {new_path}")
                    return new_path
                
                time.sleep(1)
            
            logger.warning(f"Timeout téléchargement PDF pour {country_code}{vat_number}")
            return None
            
        except Exception as e:
            logger.error(f"Erreur attente téléchargement: {e}")
            return None
    
    def cleanup(self):
        """Nettoie les ressources"""
        try:
            if self.driver:
                self.driver.quit()
                self.driver = None
            
            # Nettoyage des fichiers temporaires si nécessaire
            # (les PDF seront nettoyés après création du ZIP)
            
        except Exception as e:
            logger.error(f"Erreur lors du nettoyage: {e}")

# Tâches Celery

@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def verify_single_vat(self, country_code: str, vat_number: str, job_data: Dict = None) -> Dict:
    """
    Tâche Celery pour vérifier un seul numéro de TVA
    
    Args:
        country_code (str): Code pays
        vat_number (str): Numéro de TVA
        job_data (Dict): Données additionnelles du job
        
    Returns:
        Dict: Résultat de la vérification
    """
    automation = None
    
    try:
        logger.info(f"Début vérification Celery: {country_code}{vat_number}")
        
        # Délai aléatoire pour éviter la surcharge
        initial_delay = random.uniform(1, 5)
        time.sleep(initial_delay)
        
        # Initialisation de l'automatisation
        automation = VIESAutomation(headless=True)
        
        # Vérification
        result = automation.verify_vat_number(country_code, vat_number)
        
        # Ajout des métadonnées du job
        result.update({
            'task_id': self.request.id,
            'country_code': country_code,
            'vat_number': vat_number,
            'job_data': job_data
        })
        
        logger.info(f"Vérification Celery terminée: {country_code}{vat_number}")
        return result
        
    except Exception as exc:
        logger.error(f"Erreur vérification Celery {country_code}{vat_number}: {exc}")
        
        # Retry en cas d'erreur
        if self.request.retries < self.max_retries:
            logger.info(f"Retry #{self.request.retries + 1} pour {country_code}{vat_number}")
            raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))
        
        # Échec définitif
        return {
            'success': False,
            'is_valid': False,
            'error': f'Échec définitif après {self.max_retries} tentatives: {str(exc)}',
            'task_id': self.request.id,
            'country_code': country_code,
            'vat_number': vat_number
        }
        
    finally:
        if automation:
            automation.cleanup()

@celery.task
def process_vat_batch(vat_list: list, batch_id: str) -> Dict:
    """
    Traite un lot de numéros de TVA
    
    Args:
        vat_list (list): Liste des numéros de TVA avec métadonnées
        batch_id (str): ID du lot
        
    Returns:
        Dict: Résultats du traitement
    """
    try:
        logger.info(f"Début traitement lot {batch_id} avec {len(vat_list)} numéros")
        
        # Lancement des tâches individuelles
        job_results = []
        
        for vat_item in vat_list:
            country_code = vat_item['country_code']
            vat_number = vat_item['vat_number']
            
            # Lancement asynchrone
            task = verify_single_vat.delay(
                country_code=country_code,
                vat_number=vat_number,
                job_data={
                    'batch_id': batch_id,
                    'line_number': vat_item.get('line_number'),
                    'company_name': vat_item.get('company_name')
                }
            )
            
            job_results.append({
                'task_id': task.id,
                'country_code': country_code,
                'vat_number': vat_number,
                'status': 'launched'
            })
            
            # Délai entre les lancements pour éviter la surcharge
            time.sleep(random.uniform(0.5, 2))
        
        logger.info(f"Lot {batch_id}: {len(job_results)} tâches lancées")
        
        return {
            'batch_id': batch_id,
            'total_jobs': len(job_results),
            'launched_jobs': job_results,
            'status': 'processing'
        }
        
    except Exception as e:
        logger.error(f"Erreur traitement lot {batch_id}: {e}")
        return {
            'batch_id': batch_id,
            'error': str(e),
            'status': 'failed'
        }