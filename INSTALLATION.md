# Guide d'installation VATProof - Celery + Redis + Selenium

## Prérequis

### 1. Installation de Redis
**Windows (via Chocolatey):**
```bash
choco install redis-64
```

**Ou téléchargement direct:**
- Télécharger Redis pour Windows depuis: https://github.com/MicrosoftArchive/redis/releases
- Installer et démarrer le service Redis

**Vérification Redis:**
```bash
redis-cli ping
# Doit retourner: PONG
```

### 2. Installation de Chrome
- Télécharger Google Chrome depuis: https://www.google.com/chrome/
- S'assurer que Chrome est dans le PATH

### 3. Installation des dépendances Python
```bash
cd C:\Users\cleme\Desktop\vatproof
pip install -r requirements.txt
```

## Démarrage de l'application

### 1. Démarrage de Redis (si pas automatique)
```bash
redis-server
```

### 2. Démarrage du serveur Flask
```bash
python run.py
```

### 3. Démarrage du worker Celery (nouveau terminal)
```bash
cd C:\Users\cleme\Desktop\vatproof
celery -A worker.celery worker --loglevel=info --pool=solo
```

**Note:** Sur Windows, utilisez `--pool=solo` pour éviter les problèmes de multiprocessing.

### 4. Monitoring Celery (optionnel)
```bash
celery -A worker.celery flower
# Interface web sur http://localhost:5555
```

## Test de l'installation

### 1. Vérification des services
- Aller sur `http://127.0.0.1:5000/api/status`
- Vérifier que tous les services sont "ok":
  ```json
  {
    "status": "ok",
    "services": {
      "database": "ok",
      "redis": "ok", 
      "celery": "ok"
    }
  }
  ```

### 2. Test d'une vérification VIES
1. Aller sur `http://127.0.0.1:5000`
2. Coller quelques numéros de TVA:
   ```
   FR32552081317
   DE123456789
   IT12345678901
   ```
3. Cliquer "Analyser mes numéros"
4. Cliquer "Lancer la vérification VIES"
5. Observer la progression en temps réel

## Résolution de problèmes

### Redis ne démarre pas
```bash
# Vérifier le statut
redis-cli ping

# Redémarrer Redis
net stop redis
net start redis
```

### Celery ne trouve pas les tâches
```bash
# Vérifier que le worker est dans le bon dossier
cd C:\Users\cleme\Desktop\vatproof
celery -A worker.celery worker --loglevel=debug
```

### Selenium/Chrome ne fonctionne pas
```bash
# Installer/mettre à jour ChromeDriver automatiquement
pip install --upgrade webdriver-manager
```

### Erreur "No module named 'app.tasks'"
```bash
# S'assurer d'être dans le bon répertoire
cd C:\Users\cleme\Desktop\vatproof
python -c "import app.tasks.vies_verification; print('OK')"
```

## Architecture de production

Pour la production, voici la structure recommandée:

```
VATProof Production
├── Load Balancer (Nginx)
├── Flask App (Gunicorn)
├── Redis Cluster
├── Celery Workers (multiple machines)
├── PostgreSQL
└── File Storage (S3/Azure)
```

## Commandes utiles

```bash
# Voir les tâches en cours
celery -A worker.celery inspect active

# Voir les workers connectés  
celery -A worker.celery inspect stats

# Purger la queue
celery -A worker.celery purge

# Redémarrer un worker
celery -A worker.celery control shutdown
```