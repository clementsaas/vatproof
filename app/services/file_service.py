"""
Service de traitement des fichiers CSV/Excel
Gère l'upload, le parsing et l'extraction des numéros de TVA
"""
import pandas as pd
import io
import os
from typing import Dict, List, Optional, Any
from werkzeug.datastructures import FileStorage

class FileService:
    """Service pour le traitement des fichiers d'import"""
    
    ALLOWED_EXTENSIONS = {'.csv', '.xlsx', '.xls', '.txt'}
    MAX_ROWS = 1000  # Limite pour éviter les abus
    
    @classmethod
    def validate_file(cls, file: FileStorage) -> Dict[str, Any]:
        """
        Valide un fichier uploadé
        
        Args:
            file (FileStorage): Fichier uploadé via Flask
            
        Returns:
            Dict: Résultat de validation
        """
        result = {
            'is_valid': False,
            'error': None,
            'filename': file.filename,
            'size': 0,
            'extension': None
        }
        
        try:
            # Vérification du nom de fichier
            if not file.filename:
                result['error'] = 'Nom de fichier manquant'
                return result
            
            # Vérification de l'extension
            extension = os.path.splitext(file.filename)[1].lower()
            result['extension'] = extension
            
            if extension not in cls.ALLOWED_EXTENSIONS:
                result['error'] = f'Extension {extension} non autorisée. Extensions autorisées: {", ".join(cls.ALLOWED_EXTENSIONS)}'
                return result
            
            # Vérification de la taille (lecture du contenu)
            file_content = file.read()
            file.seek(0)  # Reset pour utilisation ultérieure
            
            result['size'] = len(file_content)
            
            if result['size'] == 0:
                result['error'] = 'Fichier vide'
                return result
            
            if result['size'] > 16 * 1024 * 1024:  # 16MB
                result['error'] = 'Fichier trop volumineux (maximum 16MB)'
                return result
            
            result['is_valid'] = True
            
        except Exception as e:
            result['error'] = f'Erreur lors de la validation: {str(e)}'
        
        return result
    
    @classmethod
    def parse_csv_file(cls, file: FileStorage) -> Dict[str, Any]:
        """
        Parse un fichier CSV
        
        Args:
            file (FileStorage): Fichier CSV
            
        Returns:
            Dict: Données parsées et métadonnées
        """
        result = {
            'success': False,
            'data': [],
            'headers': [],
            'row_count': 0,
            'error': None
        }
        
        try:
            # Lecture du contenu
            content = file.read().decode('utf-8-sig')  # utf-8-sig pour gérer BOM Excel
            file.seek(0)
            
            # Tentative de parsing avec différents délimiteurs
            delimiters = [',', ';', '\t', '|']
            df = None
            
            for delimiter in delimiters:
                try:
                    df = pd.read_csv(
                        io.StringIO(content),
                        delimiter=delimiter,
                        skip_blank_lines=True,
                        dtype=str,  # Tout en string pour éviter les conversions automatiques
                        na_filter=False  # Garde les cellules vides comme string vide
                    )
                    
                    # Si on a plus d'une colonne, c'est probablement le bon délimiteur
                    if len(df.columns) > 1 or len(df) > 1:
                        break
                        
                except:
                    continue
            
            if df is None or df.empty:
                result['error'] = 'Impossible de parser le fichier CSV'
                return result
            
            # Nettoyage des en-têtes (suppression espaces)
            df.columns = df.columns.str.strip()
            
            # Limitation du nombre de lignes
            if len(df) > cls.MAX_ROWS:
                df = df.head(cls.MAX_ROWS)
                result['warning'] = f'Fichier tronqué à {cls.MAX_ROWS} lignes'
            
            result['success'] = True
            result['data'] = df.to_dict('records')
            result['headers'] = list(df.columns)
            result['row_count'] = len(df)
            
        except UnicodeDecodeError:
            result['error'] = 'Encodage de fichier non supporté. Utilisez UTF-8.'
        except Exception as e:
            result['error'] = f'Erreur lors du parsing CSV: {str(e)}'
        
        return result
    
    @classmethod
    def parse_excel_file(cls, file: FileStorage) -> Dict[str, Any]:
        """
        Parse un fichier Excel
        
        Args:
            file (FileStorage): Fichier Excel (.xlsx, .xls)
            
        Returns:
            Dict: Données parsées et métadonnées
        """
        result = {
            'success': False,
            'data': [],
            'headers': [],
            'row_count': 0,
            'error': None,
            'sheets': []
        }
        
        try:
            # Lecture avec pandas
            file.seek(0)
            
            # Lecture de toutes les feuilles pour information
            excel_file = pd.ExcelFile(file)
            result['sheets'] = excel_file.sheet_names
            
            # Lecture de la première feuille par défaut
            df = pd.read_excel(
                file,
                sheet_name=0,  # Première feuille
                dtype=str,  # Tout en string
                na_filter=False  # Garde les cellules vides
            )
            
            if df.empty:
                result['error'] = 'Fichier Excel vide'
                return result
            
            # Nettoyage des en-têtes
            df.columns = df.columns.str.strip()
            
            # Suppression des lignes complètement vides
            df = df.dropna(how='all')
            
            # Limitation du nombre de lignes
            if len(df) > cls.MAX_ROWS:
                df = df.head(cls.MAX_ROWS)
                result['warning'] = f'Fichier tronqué à {cls.MAX_ROWS} lignes'
            
            result['success'] = True
            result['data'] = df.to_dict('records')
            result['headers'] = list(df.columns)
            result['row_count'] = len(df)
            
        except Exception as e:
            result['error'] = f'Erreur lors du parsing Excel: {str(e)}'
        
        return result
    
    @classmethod
    def parse_file(cls, file: FileStorage) -> Dict[str, Any]:
        """
        Parse un fichier selon son extension
        
        Args:
            file (FileStorage): Fichier à parser
            
        Returns:
            Dict: Résultat du parsing
        """
        # Validation préalable
        validation = cls.validate_file(file)
        if not validation['is_valid']:
            return {
                'success': False,
                'error': validation['error'],
                'filename': validation['filename']
            }
        
        # Parsing selon l'extension
        extension = validation['extension']
        
        if extension == '.csv' or extension == '.txt':
            return cls.parse_csv_file(file)
        elif extension in ['.xlsx', '.xls']:
            return cls.parse_excel_file(file)
        else:
            return {
                'success': False,
                'error': f'Type de fichier {extension} non supporté'
            }
    
    @classmethod
    def extract_vat_numbers(cls, parsed_data: Dict[str, Any], vat_column: Optional[str] = None) -> List[str]:
        """
        Extrait les numéros de TVA d'un fichier parsé
        
        Args:
            parsed_data (Dict): Données issues de parse_file()
            vat_column (str, optional): Nom de la colonne TVA (auto-détection si None)
            
        Returns:
            List[str]: Liste des numéros de TVA trouvés
        """
        if not parsed_data.get('success') or not parsed_data.get('data'):
            return []
        
        data = parsed_data['data']
        headers = parsed_data['headers']
        
        # Auto-détection de la colonne TVA si non spécifiée
        if not vat_column:
            vat_column = cls._detect_vat_column(headers)
        
        if not vat_column:
            # Si pas de colonne détectée, prendre la première colonne
            vat_column = headers[0] if headers else None
        
        if not vat_column:
            return []
        
        # Extraction des valeurs
        vat_numbers = []
        for row in data:
            vat_value = row.get(vat_column, '').strip()
            if vat_value:  # Ignore les cellules vides
                vat_numbers.append(vat_value)
        
        return vat_numbers
    
    @classmethod
    def _detect_vat_column(cls, headers: List[str]) -> Optional[str]:
        """
        Détecte automatiquement la colonne contenant les numéros de TVA
        
        Args:
            headers (List[str]): Liste des en-têtes de colonnes
            
        Returns:
            Optional[str]: Nom de la colonne TVA détectée
        """
        vat_keywords = [
            'tva', 'vat', 'numero_tva', 'numero_de_tva', 'vat_number',
            'tax', 'tax_number', 'btw', 'mwst', 'iva', 'siret', 'siren'
        ]
        
        for header in headers:
            header_lower = header.lower().replace(' ', '_').replace('-', '_')
            
            for keyword in vat_keywords:
                if keyword in header_lower:
                    return header
        
        return None
    
    @classmethod
    def parse_text_content(cls, content: str) -> List[str]:
        """
        Parse du contenu texte collé (copier-coller)
        
        Args:
            content (str): Contenu texte brut
            
        Returns:
            List[str]: Liste des numéros de TVA extraits
        """
        if not content.strip():
            return []
        
        # Séparation par lignes et nettoyage
        lines = content.strip().split('\n')
        vat_numbers = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Si la ligne contient des séparateurs (virgule, point-virgule, tabulation)
            if any(sep in line for sep in [',', ';', '\t']):
                # Prendre le premier élément (supposé être le numéro de TVA)
                parts = re.split(r'[,;\t]', line)
                if parts:
                    vat_numbers.append(parts[0].strip())
            else:
                # Ligne simple, prendre toute la ligne
                vat_numbers.append(line)
        
        return vat_numbers