"""
Point d'entrée principal pour l'application VATProof
Lance le serveur Flask en mode développement
"""
import os
import sys

# Ajout du dossier racine au PATH Python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app

# Création de l'instance Flask
app = create_app()

if __name__ == '__main__':
    # Configuration pour le développement
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '127.0.0.1')
    
    print(f"""
🛡️  VATProof - Serveur de développement
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌐 URL: http://{host}:{port}
🔧 Mode debug: {debug_mode}
📁 Environnement: {os.environ.get('FLASK_ENV', 'development')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Pour arrêter le serveur: Ctrl+C
    """)
    
    app.run(
        debug=debug_mode,
        host=host,
        port=port,
        threaded=True
    )