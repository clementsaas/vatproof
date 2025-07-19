# 🛡️ vatproof

**Plateforme de vérification massive des numéros de TVA intracommunautaire (VIES) avec génération automatique des justificatifs PDF horodatés.**

---

## 🎯 Objectif

`vatproof` permet aux cabinets comptables et aux entreprises de vérifier en masse les numéros de TVA de leurs clients sur le site officiel VIES, puis de **télécharger les justificatifs officiels PDF** générés automatiquement, horodatés, et conformes en cas de contrôle fiscal.

---

## ⚙️ Fonctionnement

1. L'utilisateur importe une liste de numéros de TVA (via fichier ou copier-coller).
2. Le système identifie automatiquement le pays à partir du numéro.
3. Un robot navigateur interroge le site officiel VIES, renseigne les champs, et télécharge les PDF.
4. Tous les justificatifs sont regroupés dans un **fichier `.zip`** téléchargeable par l’utilisateur.
5. Un tableau de bord permet de suivre l’état de chaque vérification.

---

## ✅ Pourquoi vatproof ?

- ⚖️ 100 % légal : les justificatifs sont les documents officiels VIES, sans reproduction ni transformation.
- 🔐 Conforme RGPD : aucun stockage permanent de justificatifs, traitement local ou temporaire uniquement.
- 📄 Opposable en cas de contrôle fiscal : preuve horodatée que la TVA intracom était valide au moment de la vente.
- ⚡ Scalable : conçu pour gérer des milliers de vérifications sans blocage.
- 👨‍💼 UX pensée pour les non-techniciens : interface claire, intuitive, moderne (charte inspirée d'Apple).

---

## 🧱 Stack technique (MVP)

- Python 3.11
- Flask (API + Backend)
- SQLite (début) puis PostgreSQL (scalabilité)
- Celery + Redis (gestion file d’attente)
- Playwright (robot headless VIES)
- HTML/CSS (Bootstrap 5.3) + Jinja2 (frontend)
- Authentification avec Flask-Login
- `.env` pour les variables sensibles
- Téléchargement ZIP généré à la volée

---

## 🚀 Lancer le projet en local

```bash
git clone https://github.com/ton-pseudo/vatproof.git
cd vatproof
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
flask run