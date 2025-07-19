"""
Service de validation des numéros de TVA intracommunautaire
Gère la validation, nettoyage et extraction des informations TVA
"""
import re
from typing import Dict, List, Optional, Tuple
from collections import Counter

class VATService:
    """Service pour la validation et le traitement des numéros de TVA"""
    
    # Patterns de validation par pays (source: Commission européenne)
    VAT_PATTERNS = {
        'AT': r'^U\d{8}$',                    # Autriche
        'BE': r'^\d{10}$',                    # Belgique 
        'BG': r'^\d{9,10}$',                  # Bulgarie
        'CY': r'^\d{8}[A-Z]$',                # Chypre
        'CZ': r'^\d{8,10}$',                  # République tchèque
        'DE': r'^\d{9}$',                     # Allemagne
        'DK': r'^\d{8}$',                     # Danemark
        'EE': r'^\d{9}$',                     # Estonie
        'EL': r'^\d{9}$',                     # Grèce
        'ES': r'^[A-Z]\d{7}[A-Z]$|^\d{8}[A-Z]$|^[A-Z]\d{8}$',  # Espagne
        'FI': r'^\d{8}$',                     # Finlande
        'FR': r'^[A-Z]{2}\d{9}$|^\d{11}$',   # France
        'HR': r'^\d{11}$',                    # Croatie
        'HU': r'^\d{8}$',                     # Hongrie
        'IE': r'^\d[A-Z\d]\d{5}[A-Z]$|^\d{7}[A-Z]{1,2}$',  # Irlande
        'IT': r'^\d{11}$',                    # Italie
        'LT': r'^\d{9}$|^\d{12}$',            # Lituanie
        'LU': r'^\d{8}$',                     # Luxembourg
        'LV': r'^\d{11}$',                    # Lettonie
        'MT': r'^\d{8}$',                     # Malte
        'NL': r'^\d{9}B\d{2}$',               # Pays-Bas
        'PL': r'^\d{10}$',                    # Pologne
        'PT': r'^\d{9}$',                     # Portugal
        'RO': r'^\d{2,10}$',                  # Roumanie
        'SE': r'^\d{12}$',                    # Suède
        'SI': r'^\d{8}$',                     # Slovénie
        'SK': r'^\d{10}$',                    # Slovaquie
    }
    
    # Noms complets des pays
    COUNTRY_NAMES = {
        'AT': 'Autriche', 'BE': 'Belgique', 'BG': 'Bulgarie', 'CY': 'Chypre',
        'CZ': 'République tchèque', 'DE': 'Allemagne', 'DK': 'Danemark', 
        'EE': 'Estonie', 'EL': 'Grèce', 'ES': 'Espagne', 'FI': 'Finlande',
        'FR': 'France', 'HR': 'Croatie', 'HU': 'Hongrie', 'IE': 'Irlande',
        'IT': 'Italie', 'LT': 'Lituanie', 'LU': 'Luxembourg', 'LV': 'Lettonie',
        'MT': 'Malte', 'NL': 'Pays-Bas', 'PL': 'Pologne', 'PT': 'Portugal',
        'RO': 'Roumanie', 'SE': 'Suède', 'SI': 'Slovénie', 'SK': 'Slovaquie'
    }
    
    @classmethod
    def clean_vat_number(cls, vat_input: str) -> str:
        """
        Nettoie un numéro de TVA en supprimant espaces et caractères spéciaux
        
        Args:
            vat_input (str): Numéro brut saisi par l'utilisateur
            
        Returns:
            str: Numéro nettoyé (lettres et chiffres uniquement, majuscules)
        """
        if not vat_input:
            return ''
        
        # Suppression des espaces, tirets, points, etc.
        cleaned = re.sub(r'[^A-Za-z0-9]', '', str(vat_input))
        
        # Conversion en majuscules
        return cleaned.upper()
    
    @classmethod
    def extract_country_and_number(cls, vat_input: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Extrait le code pays et le numéro de TVA
        
        Args:
            vat_input (str): Numéro de TVA complet ou partiel
            
        Returns:
            Tuple[Optional[str], Optional[str]]: (code_pays, numero) ou (None, None)
        """
        cleaned = cls.clean_vat_number(vat_input)
        
        if len(cleaned) < 3:
            return None, None
        
        # Si commence par 2 lettres, c'est probablement un code pays
        country_match = re.match(r'^([A-Z]{2})(.+)$', cleaned)
        if country_match:
            country_code = country_match.group(1)
            vat_number = country_match.group(2)
            
            # Vérification que le code pays est valide
            if country_code in cls.VAT_PATTERNS:
                return country_code, vat_number
        
        # Sinon, retourner le numéro entier (pays à déterminer manuellement)
        return None, cleaned
    
    @classmethod
    def validate_vat_format(cls, country_code: str, vat_number: str) -> Dict[str, any]:
        """
        Valide le format d'un numéro de TVA selon les règles du pays
        
        Args:
            country_code (str): Code pays ISO (2 lettres)
            vat_number (str): Numéro de TVA sans le code pays
            
        Returns:
            Dict: Résultat de validation avec détails
        """
        result = {
            'is_valid': False,
            'country_code': country_code,
            'vat_number': vat_number,
            'country_name': cls.COUNTRY_NAMES.get(country_code, country_code),
            'error': None
        }
        
        # Vérification que le pays existe
        if country_code not in cls.VAT_PATTERNS:
            result['error'] = f"Code pays '{country_code}' non reconnu ou non supporté par VIES"
            return result
        
        # Vérification du format selon le pattern du pays
        pattern = cls.VAT_PATTERNS[country_code]
        if re.match(pattern, vat_number):
            result['is_valid'] = True
        else:
            result['error'] = f"Format invalide pour {result['country_name']} (attendu: {pattern})"
        
        return result
    
    @classmethod
    def validate_single_vat(cls, vat_input: str, line_number: int = None) -> Dict[str, any]:
        """
        Valide un seul numéro de TVA
        
        Args:
            vat_input (str): Numéro de TVA brut
            line_number (int): Numéro de ligne dans le fichier (optionnel)
            
        Returns:
            Dict: Résultat complet de validation
        """
        result = {
            'original': vat_input,
            'cleaned': '',
            'country_code': None,
            'vat_number': None,
            'is_valid': False,
            'line_number': line_number,
            'error': None,
            'country_name': None
        }
        
        # Nettoyage
        cleaned = cls.clean_vat_number(vat_input)
        result['cleaned'] = cleaned
        
        if not cleaned:
            result['error'] = 'Numéro vide ou invalide'
            return result
        
        if len(cleaned) < 3:
            result['error'] = 'Numéro trop court (minimum 3 caractères)'
            return result
        
        if len(cleaned) > 15:
            result['error'] = 'Numéro trop long (maximum 15 caractères)'
            return result
        
        # Extraction du pays et numéro
        country_code, vat_number = cls.extract_country_and_number(cleaned)
        
        if not country_code:
            result['error'] = 'Code pays manquant ou invalide (doit commencer par 2 lettres)'
            return result
        
        result['country_code'] = country_code
        result['vat_number'] = vat_number
        result['country_name'] = cls.COUNTRY_NAMES.get(country_code, country_code)
        
        # Validation du format
        format_validation = cls.validate_vat_format(country_code, vat_number)
        result['is_valid'] = format_validation['is_valid']
        result['error'] = format_validation['error']
        
        return result
    
    @classmethod
    def validate_vat_list(cls, vat_list: List[str]) -> Dict[str, any]:
        """
        Valide une liste de numéros de TVA
        
        Args:
            vat_list (List[str]): Liste des numéros à valider
            
        Returns:
            Dict: Résultats de validation avec statistiques
        """
        if not vat_list:
            return {
                'valid': [],
                'invalid': [],
                'duplicates': [],
                'summary': {
                    'total_count': 0,
                    'valid_count': 0,
                    'invalid_count': 0,
                    'duplicate_count': 0,
                    'countries': {}
                }
            }
        
        valid_results = []
        invalid_results = []
        seen_numbers = {}  # Pour détecter les doublons
        countries = Counter()
        
        for line_number, vat_input in enumerate(vat_list, 1):
            # Validation individuelle
            validation_result = cls.validate_single_vat(vat_input, line_number)
            
            # Détection des doublons
            if validation_result['is_valid']:
                full_vat = f"{validation_result['country_code']}{validation_result['vat_number']}"
                
                if full_vat in seen_numbers:
                    # Marquer comme doublon
                    validation_result['is_duplicate'] = True
                    validation_result['duplicate_of_line'] = seen_numbers[full_vat]
                    validation_result['error'] = f"Doublon de la ligne {seen_numbers[full_vat]}"
                else:
                    seen_numbers[full_vat] = line_number
                    validation_result['is_duplicate'] = False
                    
                    # Comptage par pays (seulement pour les non-doublons)
                    countries[validation_result['country_code']] += 1
                
                valid_results.append(validation_result)
            else:
                validation_result['is_duplicate'] = False
                invalid_results.append(validation_result)
        
        # Statistiques
        duplicate_count = len([v for v in valid_results if v.get('is_duplicate')])
        
        summary = {
            'total_count': len(vat_list),
            'valid_count': len(valid_results) - duplicate_count,  # Valides non-doublons
            'invalid_count': len(invalid_results),
            'duplicate_count': duplicate_count,
            'countries': dict(countries)
        }
        
        return {
            'valid': valid_results,
            'invalid': invalid_results,
            'duplicates': [v for v in valid_results if v.get('is_duplicate')],
            'summary': summary
        }
    
    @classmethod
    def get_country_name(cls, country_code: str) -> str:
        """
        Récupère le nom complet d'un pays depuis son code
        
        Args:
            country_code (str): Code pays ISO (2 lettres)
            
        Returns:
            str: Nom du pays ou code si non trouvé
        """
        return cls.COUNTRY_NAMES.get(country_code, country_code)
    
    @classmethod
    def get_supported_countries(cls) -> Dict[str, str]:
        """
        Retourne la liste des pays supportés par VIES
        
        Returns:
            Dict[str, str]: Dictionnaire {code: nom_pays}
        """
        return cls.COUNTRY_NAMES.copy()
    
    @classmethod
    def prepare_for_vies_verification(cls, validation_results: Dict) -> List[Dict]:
        """
        Prépare les numéros valides pour la vérification VIES
        
        Args:
            validation_results (Dict): Résultats de validate_vat_list()
            
        Returns:
            List[Dict]: Liste des jobs à envoyer à Celery
        """
        jobs = []
        
        # Prendre uniquement les numéros valides et non-doublons
        for result in validation_results['valid']:
            if not result.get('is_duplicate'):
                job_data = {
                    'country_code': result['country_code'],
                    'vat_number': result['vat_number'],
                    'original_input': result['original'],
                    'line_number': result['line_number'],
                    'company_name': None  # Sera rempli par VIES si trouvé
                }
                jobs.append(job_data)
        
        return jobs
    
    @classmethod
    def format_vat_display(cls, country_code: str, vat_number: str) -> str:
        """
        Formate un numéro de TVA pour l'affichage
        
        Args:
            country_code (str): Code pays
            vat_number (str): Numéro de TVA
            
        Returns:
            str: Numéro formaté (ex: "FR 12 345 678 901")
        """
        if not country_code or not vat_number:
            return ''
        
        # Formatage spécifique par pays pour l'affichage
        full_number = f"{country_code}{vat_number}"
        
        # France: FR 12 345 678 901
        if country_code == 'FR' and len(vat_number) == 11:
            return f"FR {vat_number[:2]} {vat_number[2:5]} {vat_number[5:8]} {vat_number[8:11]}"
        
        # Allemagne: DE 123 456 789
        elif country_code == 'DE' and len(vat_number) == 9:
            return f"DE {vat_number[:3]} {vat_number[3:6]} {vat_number[6:9]}"
        
        # Italie: IT 12345678901
        elif country_code == 'IT' and len(vat_number) == 11:
            return f"IT {vat_number[:5]} {vat_number[5:10]} {vat_number[10]}"
        
        # Espagne: ES A12345674
        elif country_code == 'ES':
            return f"ES {vat_number}"
        
        # Pays-Bas: NL 123456789B01
        elif country_code == 'NL':
            return f"NL {vat_number[:9]} {vat_number[9:]}"
        
        # Format par défaut: pays + espace + numéro
        else:
            return f"{country_code} {vat_number}"
    
    @classmethod
    def generate_validation_report(cls, validation_results: Dict, filename: str = None) -> str:
        """
        Génère un rapport de validation lisible
        
        Args:
            validation_results (Dict): Résultats de validate_vat_list()
            filename (str): Nom du fichier source (optionnel)
            
        Returns:
            str: Rapport formaté
        """
        summary = validation_results['summary']
        
        report = f"""RAPPORT DE VALIDATION TVA
{'='*50}

Fichier source: {filename or 'Saisie manuelle'}
Date: {cls._get_current_datetime()}

RÉSUMÉ:
- Total de numéros analysés: {summary['total_count']}
- Numéros valides: {summary['valid_count']}
- Numéros invalides: {summary['invalid_count']}
- Doublons détectés: {summary['duplicate_count']}

RÉPARTITION PAR PAYS:
"""
        
        # Ajout de la répartition par pays
        if summary['countries']:
            for country_code, count in sorted(summary['countries'].items()):
                country_name = cls.get_country_name(country_code)
                report += f"- {country_name} ({country_code}): {count} numéro(s)\n"
        else:
            report += "- Aucun pays détecté\n"
        
        # Détail des erreurs si il y en a
        if validation_results['invalid']:
            report += f"\nERREURS DÉTECTÉES ({len(validation_results['invalid'])}):\n"
            report += "-" * 40 + "\n"
            
            for invalid in validation_results['invalid'][:10]:  # Limite à 10 erreurs
                report += f"Ligne {invalid['line_number']}: '{invalid['original']}' - {invalid['error']}\n"
            
            if len(validation_results['invalid']) > 10:
                report += f"... et {len(validation_results['invalid']) - 10} autre(s) erreur(s)\n"
        
        # Détail des doublons si il y en a
        if validation_results['duplicates']:
            report += f"\nDOUBLONS DÉTECTÉS ({len(validation_results['duplicates'])}):\n"
            report += "-" * 40 + "\n"
            
            for duplicate in validation_results['duplicates'][:10]:  # Limite à 10 doublons
                original_line = duplicate.get('duplicate_of_line', '?')
                report += f"Ligne {duplicate['line_number']}: '{duplicate['original']}' (identique à ligne {original_line})\n"
            
            if len(validation_results['duplicates']) > 10:
                report += f"... et {len(validation_results['duplicates']) - 10} autre(s) doublon(s)\n"
        
        report += f"\n{'='*50}\n"
        report += "Rapport généré par VATProof\n"
        
        return report
    
    @classmethod
    def _get_current_datetime(cls) -> str:
        """Retourne la date/heure actuelle formatée"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    @classmethod
    def extract_vat_from_mixed_content(cls, content: str) -> List[str]:
        """
        Extrait les numéros de TVA d'un contenu mixte (texte libre)
        
        Args:
            content (str): Contenu textuel pouvant contenir des numéros de TVA
            
        Returns:
            List[str]: Liste des numéros de TVA détectés
        """
        if not content:
            return []
        
        # Pattern pour détecter les numéros de TVA dans du texte libre
        # Cherche: 2 lettres + 8-12 chiffres/lettres
        vat_pattern = r'\b([A-Z]{2})[\s\-\.]?([A-Z0-9]{8,12})\b'
        
        matches = re.findall(vat_pattern, content.upper())
        vat_numbers = []
        
        for country, number in matches:
            # Vérification basique que c'est un pays EU
            if country in cls.VAT_PATTERNS:
                vat_numbers.append(f"{country}{number}")
        
        return vat_numbers
    
    @classmethod
    def suggest_corrections(cls, invalid_vat: str) -> List[str]:
        """
        Suggère des corrections pour un numéro de TVA invalide
        
        Args:
            invalid_vat (str): Numéro de TVA invalide
            
        Returns:
            List[str]: Liste de suggestions de correction
        """
        suggestions = []
        cleaned = cls.clean_vat_number(invalid_vat)
        
        if not cleaned:
            return ["Saisir un numéro de TVA non vide"]
        
        # Si pas de code pays
        if len(cleaned) < 2 or not cleaned[:2].isalpha():
            suggestions.append("Ajouter le code pays au début (ex: FR, DE, IT, ES...)")
            return suggestions
        
        country_code = cleaned[:2]
        vat_number = cleaned[2:]
        
        # Si code pays invalide, suggérer les plus proches
        if country_code not in cls.VAT_PATTERNS:
            close_countries = [c for c in cls.VAT_PATTERNS.keys() 
                             if c[0] == country_code[0] or c[1] == country_code[1]]
            if close_countries:
                suggestions.append(f"Code pays '{country_code}' invalide. Essayez: {', '.join(close_countries[:3])}")
        
        # Vérification de la longueur selon le pays
        if country_code in cls.VAT_PATTERNS:
            pattern = cls.VAT_PATTERNS[country_code]
            
            # Analyse du pattern pour suggérer la longueur attendue
            if 'FR' == country_code:
                if len(vat_number) != 11:
                    suggestions.append("Numéro français: 11 chiffres attendus après FR")
            elif 'DE' == country_code:
                if len(vat_number) != 9:
                    suggestions.append("Numéro allemand: 9 chiffres attendus après DE")
            elif 'IT' == country_code:
                if len(vat_number) != 11:
                    suggestions.append("Numéro italien: 11 chiffres attendus après IT")
        
        if not suggestions:
            suggestions.append("Vérifier le format selon le pays d'origine")
        
        return suggestions