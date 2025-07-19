/**
 * VATProof - JavaScript principal
 * Gestion des interactions utilisateur et des appels API
 */

// Configuration globale
const VATProof = {
    config: {
        apiBaseUrl: '/api',
        pollInterval: 5000, // 5 secondes
        maxFileSize: 16 * 1024 * 1024, // 16 MB
        allowedExtensions: ['.csv', '.xlsx', '.xls', '.txt']
    },
    
    // État global de l'application
    state: {
        currentJobId: null,
        isPolling: false,
        uploadedData: null
    }
};

/**
 * Utilitaires généraux
 */
const Utils = {
    
    /**
     * Affiche un toast de notification
     */
    showToast(message, type = 'info') {
        // TODO: Implémenter un système de toast
        console.log(`[${type.toUpperCase()}] ${message}`);
        
        // Pour l'instant, utilisation d'alert pour les erreurs critiques
        if (type === 'error') {
            alert(message);
        }
    },
    
    /**
     * Valide l'extension d'un fichier
     */
    validateFileExtension(filename) {
        const extension = '.' + filename.split('.').pop().toLowerCase();
        return VATProof.config.allowedExtensions.includes(extension);
    },
    
    /**
     * Valide la taille d'un fichier
     */
    validateFileSize(file) {
        return file.size <= VATProof.config.maxFileSize;
    },
    
    /**
     * Formate la taille d'un fichier
     */
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    },
    
    /**
     * Affiche un overlay de chargement
     */
    showLoading(message = 'Chargement...') {
        let overlay = document.getElementById('loadingOverlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'loadingOverlay';
            overlay.className = 'loading-overlay';
            overlay.innerHTML = `
                <div class="text-center">
                    <div class="loading-spinner mb-3"></div>
                    <div class="fw-bold" id="loadingMessage">${message}</div>
                </div>
            `;
            document.body.appendChild(overlay);
        } else {
            document.getElementById('loadingMessage').textContent = message;
            overlay.style.display = 'flex';
        }
    },
    
    /**
     * Masque l'overlay de chargement
     */
    hideLoading() {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) {
            overlay.style.display = 'none';
        }
    },
    
    /**
     * Effectue un appel API
     */
    async apiCall(endpoint, options = {}) {
        const url = VATProof.config.apiBaseUrl + endpoint;
        
        try {
            const response = await fetch(url, {
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers
                },
                ...options
            });
            
            if (!response.ok) {
                throw new Error(`Erreur ${response.status}: ${response.statusText}`);
            }
            
            return await response.json();
        } catch (error) {
            console.error('Erreur API:', error);
            throw error;
        }
    }
};

/**
 * Gestion des fichiers et de l'upload
 */
const FileManager = {
    
    /**
     * Traite l'upload d'un fichier
     */
    async handleFileUpload(file) {
        // Validation
        if (!Utils.validateFileExtension(file.name)) {
            Utils.showToast('Format de fichier non supporté', 'error');
            return false;
        }
        
        if (!Utils.validateFileSize(file)) {
            Utils.showToast(`Fichier trop volumineux (max ${Utils.formatFileSize(VATProof.config.maxFileSize)})`, 'error');
            return false;
        }
        
        // Préparation du FormData
        const formData = new FormData();
        formData.append('file', file);
        
        Utils.showLoading('Analyse du fichier en cours...');
        
        try {
            const response = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });
            
            const data = await response.json();
            Utils.hideLoading();
            
            if (data.error) {
                Utils.showToast(data.error, 'error');
                return false;
            }
            
            // Stockage des données pour utilisation ultérieure
            VATProof.state.uploadedData = data;
            
            // Affichage de la prévisualisation
            PreviewManager.showPreview(data);
            
            return true;
            
        } catch (error) {
            Utils.hideLoading();
            Utils.showToast('Erreur lors de l\'upload du fichier', 'error');
            console.error('Erreur upload:', error);
            return false;
        }
    },
    
    /**
     * Traite le texte collé
     */
    async handlePasteContent(content) {
        if (!content.trim()) {
            Utils.showToast('Veuillez saisir au moins un numéro de TVA', 'error');
            return false;
        }
        
        Utils.showLoading('Analyse de la liste en cours...');
        
        try {
            const data = await Utils.apiCall('/verify-paste', {
                method: 'POST',
                body: JSON.stringify({ content: content })
            });
            
            Utils.hideLoading();
            
            // Stockage des données
            VATProof.state.uploadedData = data;
            
            // Affichage de la prévisualisation
            PreviewManager.showPreview(data);
            
            return true;
            
        } catch (error) {
            Utils.hideLoading();
            Utils.showToast('Erreur lors de l\'analyse de la liste', 'error');
            console.error('Erreur paste:', error);
            return false;
        }
    }
};

/**
 * Gestion de la prévisualisation des données
 */
const PreviewManager = {
    
    /**
     * Affiche la prévisualisation des données importées
     */
    showPreview(data) {
        const previewSection = document.getElementById('previewSection');
        const previewContent = document.getElementById('previewContent');
        const validCount = document.getElementById('validCount');
        
        if (!previewSection || !previewContent || !validCount) {
            console.error('Éléments de prévisualisation manquants');
            return;
        }
        
        // Mise à jour du compteur
        validCount.textContent = data.lines_count || 0;
        
        // Génération du tableau de prévisualisation
        let html = '<div class="table-responsive">';
        html += '<table class="table table-hover">';
        html += '<thead class="table-light">';
        html += '<tr><th>N°</th><th>Numéro TVA</th><th>Pays</th><th>Statut</th></tr>';
        html += '</thead><tbody>';
        
        if (data.preview && data.preview.length > 0) {
            data.preview.forEach((line, index) => {
                // Extraction du code pays (2 premières lettres)
                const countryCode = line.substring(0, 2).toUpperCase();
                const vatNumber = line.substring(2);
                
                html += `
                    <tr>
                        <td>${index + 1}</td>
                        <td><code>${line}</code></td>
                        <td><span class="badge bg-info">${countryCode}</span></td>
                        <td><span class="badge bg-secondary">À vérifier</span></td>
                    </tr>
                `;
            });
        }
        
        html += '</tbody></table></div>';
        
        // Affichage du nombre total si supérieur à l'aperçu
        if (data.lines_count > 5) {
            html += `<p class="text-muted small mt-2">
                <i class="bi bi-info-circle me-1"></i>
                Aperçu des 5 premiers numéros sur ${data.lines_count} au total
            </p>`;
        }
        
        previewContent.innerHTML = html;
        previewSection.classList.remove('d-none');
        
        // Configuration du bouton de vérification
        const startBtn = document.getElementById('startVerificationBtn');
        if (startBtn) {
            startBtn.onclick = () => VerificationManager.startVerification(data);
        }
        
        // Animation d'apparition
        previewSection.classList.add('fade-in');
    }
};

/**
 * Gestion des vérifications
 */
const VerificationManager = {
    
    /**
     * Démarre le processus de vérification
     */
    async startVerification(data) {
        if (!data || !data.job_id) {
            Utils.showToast('Données de vérification manquantes', 'error');
            return;
        }
        
        // Stockage de l'ID du job
        VATProof.state.currentJobId = data.job_id;
        
        // Masquage de la prévisualisation et affichage de la progression
        const previewSection = document.getElementById('previewSection');
        const progressSection = document.getElementById('progressSection');
        
        if (previewSection) previewSection.classList.add('d-none');
        if (progressSection) progressSection.classList.remove('d-none');
        
        // Démarrage du polling pour suivre la progression
        this.startPolling();
        
        Utils.showToast('Vérification démarrée', 'success');
    },
    
    /**
     * Démarre le polling pour suivre la progression
     */
    startPolling() {
        if (VATProof.state.isPolling) return;
        
        VATProof.state.isPolling = true;
        
        const poll = async () => {
            if (!VATProof.state.isPolling || !VATProof.state.currentJobId) {
                return;
            }
            
            try {
                const status = await Utils.apiCall(`/jobs/${VATProof.state.currentJobId}/status`);
                this.updateProgress(status);
                
                // Continuer le polling si pas terminé
                if (status.status !== 'completed' && status.status !== 'failed') {
                    setTimeout(poll, VATProof.config.pollInterval);
                } else {
                    this.handleCompletion(status);
                }
                
            } catch (error) {
                console.error('Erreur polling:', error);
                // Retry dans 10 secondes en cas d'erreur
                setTimeout(poll, 10000);
            }
        };
        
        // Démarrage immédiat du premier poll
        poll();
    },
    
    /**
     * Met à jour l'affichage de progression
     */
    updateProgress(status) {
        const progress = status.progress || {};
        const total = progress.total || 0;
        const completed = progress.completed || 0;
        const failed = progress.failed || 0;
        const inProgress = progress.in_progress || 0;
        const pending = total - completed - failed - inProgress;
        
        // Calcul du pourcentage
        const percentage = total > 0 ? Math.round(((completed + failed) / total) * 100) : 0;
        
        // Mise à jour de la barre de progression
        const progressBar = document.getElementById('progressBar');
        if (progressBar) {
            progressBar.style.width = percentage + '%';
            progressBar.textContent = percentage + '%';
        }
        
        // Mise à jour des compteurs
        const elements = {
            pendingCount: pending,
            processingCount: inProgress,
            completedCount: completed,
            errorCount: failed
        };
        
        Object.entries(elements).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element) element.textContent = value;
        });
    },
    
    /**
     * Gère la fin de la vérification
     */
    handleCompletion(status) {
        VATProof.state.isPolling = false;
        
        const progressSection = document.getElementById('progressSection');
        const downloadSection = document.getElementById('downloadSection');
        
        if (progressSection) progressSection.classList.add('d-none');
        
        if (status.status === 'completed') {
            // Affichage de la section de téléchargement
            if (downloadSection) {
                downloadSection.classList.remove('d-none');
                downloadSection.classList.add('fade-in');
            }
            
            // Configuration du bouton de téléchargement
            const downloadBtn = document.getElementById('downloadZipBtn');
            if (downloadBtn) {
                downloadBtn.onclick = () => this.downloadResults();
            }
            
            Utils.showToast('Vérification terminée avec succès', 'success');
        } else {
            Utils.showToast('Erreur lors de la vérification', 'error');
        }
    },
    
    /**
     * Télécharge les résultats
     */
    async downloadResults() {
        // TODO: Implémenter le téléchargement du ZIP
        Utils.showToast('Téléchargement des résultats (à implémenter)', 'info');
    }
};

/**
 * Initialisation de l'application
 */
document.addEventListener('DOMContentLoaded', function() {
    console.log('VATProof - Application initialisée');
    
    // Vérification de la présence des éléments sur la page d'accueil
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('fileInput');
    const pasteForm = document.getElementById('pasteForm');
    
    if (dropzone && fileInput) {
        // Configuration du drag & drop
        setupDragAndDrop();
    }
    
    if (pasteForm) {
        // Configuration du formulaire de paste
        setupPasteForm();
    }
    
    // Vérification périodique du statut système
    setInterval(checkSystemStatus, 30000);
    checkSystemStatus(); // Vérification initiale
});

/**
 * Configuration du drag & drop
 */
function setupDragAndDrop() {
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('fileInput');
    
    // Clic sur la dropzone
    dropzone.addEventListener('click', () => fileInput.click());
    
    // Drag & drop events
    dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.classList.add('border-primary', 'bg-light');
    });
    
    dropzone.addEventListener('dragleave', (e) => {
        e.preventDefault();
        if (!dropzone.contains(e.relatedTarget)) {
            dropzone.classList.remove('border-primary', 'bg-light');
        }
    });
    
    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('border-primary', 'bg-light');
        
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            FileManager.handleFileUpload(files[0]);
        }
    });
    
    // Changement de fichier via l'input
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            FileManager.handleFileUpload(e.target.files[0]);
        }
    });
}

/**
 * Configuration du formulaire de paste
 */
function setupPasteForm() {
    const pasteForm = document.getElementById('pasteForm');
    const vatList = document.getElementById('vatList');
    const clearBtn = document.getElementById('clearBtn');
    
    pasteForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const content = vatList.value.trim();
        FileManager.handlePasteContent(content);
    });
    
    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            vatList.value = '';
            vatList.focus();
        });
    }
}

/**
 * Vérification du statut système
 */
async function checkSystemStatus() {
    try {
        const status = await Utils.apiCall('/status');
        const statusElement = document.getElementById('system-status');
        
        if (statusElement) {
            if (status.status === 'ok') {
                statusElement.className = 'badge bg-success';
                statusElement.textContent = 'En ligne';
            } else {
                statusElement.className = 'badge bg-warning';
                statusElement.textContent = 'Limité';
            }
        }
    } catch (error) {
        const statusElement = document.getElementById('system-status');
        if (statusElement) {
            statusElement.className = 'badge bg-danger';
            statusElement.textContent = 'Hors ligne';
        }
        console.error('Erreur vérification statut:', error);
    }
}