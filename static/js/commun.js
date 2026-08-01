/* Helpers partagés par toutes les pages de Divix Maquis. */

const Divix = {
    /* ------------------------------------------------------------------ */
    /* Formatage                                                          */
    /* ------------------------------------------------------------------ */

    montant(valeur) {
        return new Intl.NumberFormat('fr-FR', {
            minimumFractionDigits: 0,
            maximumFractionDigits: 0
        }).format(Number(valeur) || 0);
    },

    fcfa(valeur) {
        return `${Divix.montant(valeur)} FCFA`;
    },

    date(valeur, avecHeure = false) {
        if (!valeur) return '—';
        const date = new Date(String(valeur).replace(' ', 'T'));
        if (Number.isNaN(date.getTime())) return valeur;
        const options = { year: 'numeric', month: 'short', day: '2-digit' };
        if (avecHeure) {
            options.hour = '2-digit';
            options.minute = '2-digit';
        }
        return date.toLocaleString('fr-FR', options);
    },

    heure(valeur) {
        if (!valeur) return '—';
        const date = new Date(String(valeur).replace(' ', 'T'));
        if (Number.isNaN(date.getTime())) return '—';
        return date.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
    },

    echapper(texte) {
        const div = document.createElement('div');
        div.textContent = texte ?? '';
        return div.innerHTML;
    },

    /* ------------------------------------------------------------------ */
    /* Badges                                                             */
    /* ------------------------------------------------------------------ */

    classeStatut(statut) {
        const correspondances = {
            'Payée': 'badge-success',
            'Servie': 'badge-success',
            'En cours': 'badge-pending',
            'Annulée': 'badge-danger',
            'En stock': 'badge-success',
            'Préparé': 'badge-success',
            'Stock faible': 'badge-pending',
            'Rupture': 'badge-danger',
            'Libre': 'badge-success',
            'Occupée': 'badge-pending',
            'Réservée': 'badge-danger',
            'Entrée': 'badge-success',
            'Sortie': 'badge-pending',
            'Perte': 'badge-danger',
            'Inventaire': 'badge-success'
        };
        return correspondances[statut] || 'badge-success';
    },

    badge(statut) {
        return `<span class="badge ${Divix.classeStatut(statut)}">${Divix.echapper(statut)}</span>`;
    },

    /* ------------------------------------------------------------------ */
    /* États des tableaux                                                 */
    /* ------------------------------------------------------------------ */

    chargement(idTbody, colonnes = 8) {
        const conteneur = document.getElementById(idTbody);
        if (!conteneur) return;
        conteneur.innerHTML = `
            <tr class="line-nothing">
                <td colspan="${colonnes}" class="table-spinner nothing">
                    <div class="dots-loader m-0"><span></span><span></span><span></span></div>
                    <p class="text-muted small m-0 mt-2 mb-0">Chargement des données...</p>
                </td>
            </tr>`;
    },

    vide(idTbody, message, colonnes = 8) {
        const conteneur = document.getElementById(idTbody);
        if (!conteneur) return;
        conteneur.innerHTML = `
            <tr class="line-nothing">
                <td colspan="${colonnes}" class="text-center py-5 nothing">
                    <i class="bi bi-inbox fs-1 text-muted"></i>
                    <p class="text-muted mt-2 mb-0">${Divix.echapper(message)}</p>
                </td>
            </tr>`;
    },

    /* ------------------------------------------------------------------ */
    /* Compteurs animés                                                   */
    /* ------------------------------------------------------------------ */

    animerNombre(element, cible, duree = 900) {
        if (!element) return;   // la carte peut être masquée par un module désactivé
        const depart = 0;
        let debut = null;
        const etape = (horodatage) => {
            if (!debut) debut = horodatage;
            const progression = Math.min((horodatage - debut) / duree, 1);
            const valeur = Math.floor(progression * (cible - depart) + depart);
            element.textContent = Divix.montant(valeur);
            if (progression < 1) window.requestAnimationFrame(etape);
        };
        window.requestAnimationFrame(etape);
    },

    /**
     * Met à jour les <span id="counter{clé}"> à partir d'un objet de compteurs.
     */
    compteurs(donnees, prefixe = 'counter') {
        if (!donnees) return;
        Object.entries(donnees).forEach(([cle, valeur]) => {
            const element = document.getElementById(`${prefixe}${cle}`);
            if (!element) return;
            element.classList.remove('counter-skeleton');
            Divix.animerNombre(element, Number(valeur) || 0);
        });
    },

    squelette(ids, actif = true) {
        ids.forEach((id) => {
            const element = document.getElementById(id);
            if (element) element.classList.toggle('counter-skeleton', actif);
        });
    },

    /* ------------------------------------------------------------------ */
    /* Réseau                                                             */
    /* ------------------------------------------------------------------ */

    async charger(url) {
        const reponse = await fetch(url);
        if (!reponse.ok) throw new Error(`Erreur ${reponse.status} sur ${url}`);
        return reponse.json();
    },

    /**
     * Envoie un formulaire en POST et affiche le retour via SweetAlert.
     * `donnees` accepte un FormData ou un objet simple.
     */
    async envoyer(url, donnees) {
        const corps = donnees instanceof FormData ? donnees : Divix.versFormData(donnees);
        const reponse = await fetch(url, { method: 'POST', body: corps });
        return reponse.json();
    },

    versFormData(objet) {
        const formData = new FormData();
        Object.entries(objet).forEach(([cle, valeur]) => formData.append(cle, valeur));
        return formData;
    },

    succes(message) {
        return Swal.fire({
            icon: 'success',
            title: 'Succès',
            text: message,
            confirmButtonColor: '#3d6dff',
            timer: 1400
        });
    },

    erreur(message) {
        return Swal.fire({
            icon: 'error',
            title: 'Erreur',
            text: message || "Une erreur est survenue",
            confirmButtonColor: '#3d6dff'
        });
    },

    /**
     * Branche un bouton de soumission sur un endpoint.
     * `avantEnvoi` peut renvoyer false pour annuler, ou un FormData personnalisé.
     */
    brancherFormulaire({ idBouton, idFormulaire, url, idModal, apres, avantEnvoi }) {
        const bouton = document.getElementById(idBouton);
        const formulaire = document.getElementById(idFormulaire);
        if (!bouton || !formulaire) return;

        bouton.addEventListener('click', async () => {
            if (!formulaire.reportValidity()) return;

            let donnees = new FormData(formulaire);
            if (avantEnvoi) {
                const resultat = avantEnvoi(donnees);
                if (resultat === false) return;
                if (resultat instanceof FormData) donnees = resultat;
            }

            const texteOrigine = bouton.innerHTML;
            bouton.disabled = true;
            bouton.innerHTML = '<i class="bx bx-loader-circle bx-spin me-2"></i>Enregistrement...';

            try {
                const reponse = await Divix.envoyer(url, donnees);
                if (reponse.success) {
                    await Divix.succes(reponse.message || 'Opération réussie');
                    const modal = idModal && bootstrap.Modal.getInstance(document.getElementById(idModal));
                    if (modal) modal.hide();
                    formulaire.reset();
                    if (apres) apres(reponse);
                } else {
                    await Divix.erreur(reponse.error);
                }
            } catch (erreur) {
                console.error(erreur);
                await Divix.erreur("Impossible de contacter le serveur");
            } finally {
                bouton.disabled = false;
                bouton.innerHTML = texteOrigine;
            }
        });
    },

    /* ------------------------------------------------------------------ */
    /* Filtres de tableau                                                 */
    /* ------------------------------------------------------------------ */

    /**
     * Filtre les lignes d'un tbody sur un texte libre et/ou un attribut data.
     */
    brancherFiltres({ idTbody, idRecherche, filtres = [] }) {
        const tbody = document.getElementById(idTbody);
        if (!tbody) return;

        const appliquer = () => {
            const recherche = (document.getElementById(idRecherche)?.value || '')
                .toLowerCase()
                .trim();

            tbody.querySelectorAll('tr').forEach((ligne) => {
                if (ligne.classList.contains('line-nothing')) return;

                const correspondTexte = !recherche
                    || ligne.textContent.toLowerCase().includes(recherche);

                const correspondFiltres = filtres.every(({ idSelect, attribut }) => {
                    const valeur = document.getElementById(idSelect)?.value;
                    return !valeur || ligne.dataset[attribut] === valeur;
                });

                ligne.style.display = correspondTexte && correspondFiltres ? '' : 'none';
            });
        };

        document.getElementById(idRecherche)?.addEventListener('input', appliquer);
        filtres.forEach(({ idSelect }) => {
            document.getElementById(idSelect)?.addEventListener('change', appliquer);
        });

        return appliquer;
    }
};

/* Horloge de service affichée dans la barre du haut. */
document.addEventListener('DOMContentLoaded', () => {
    const horloge = document.getElementById('horloge-service');
    if (!horloge) return;

    const rafraichir = () => {
        horloge.textContent = new Date().toLocaleString('fr-FR', {
            weekday: 'long',
            day: '2-digit',
            month: 'long',
            hour: '2-digit',
            minute: '2-digit'
        });
    };
    rafraichir();
    setInterval(rafraichir, 30000);
});
