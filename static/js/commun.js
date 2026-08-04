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
                    <i class="bxf bx-inbox fs-1 text-muted"></i>
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
    /* `urlDynamique` permet à un même formulaire de créer ou de modifier. */
    brancherFormulaire({ idBouton, idFormulaire, url, urlDynamique, idModal, apres, avantEnvoi }) {
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
            bouton.innerHTML = '<i class="bx bx-loader-lines bx-spin me-2"></i>Enregistrement...';

            try {
                const reponse = await Divix.envoyer(urlDynamique ? urlDynamique() : url, donnees);
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
    /* `apres` sert à réappliquer la pagination une fois le filtrage terminé. */
    brancherFiltres({ idTbody, idRecherche, filtres = [], apres = null }) {
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

                // Une classe plutôt que style.display : la pagination masque de
                // son côté, les deux ne doivent pas s'écraser mutuellement.
                ligne.classList.toggle(
                    'filtre-masque', !(correspondTexte && correspondFiltres)
                );
            });

            apres?.();
        };

        document.getElementById(idRecherche)?.addEventListener('input', appliquer);
        filtres.forEach(({ idSelect }) => {
            document.getElementById(idSelect)?.addEventListener('change', appliquer);
        });

        return appliquer;
    },

    /* ------------------------------------------------------------------ */
    /* Pagination                                                         */
    /* ------------------------------------------------------------------ */

    _numerosPages(courante, total) {
        if (total <= 5) {
            return Array.from({ length: total }, (_, index) => index + 1);
        }
        const pages = [1];
        if (courante > 3) pages.push('…');
        for (let p = Math.max(2, courante - 1); p <= Math.min(total - 1, courante + 1); p += 1) {
            pages.push(p);
        }
        if (courante < total - 2) pages.push('…');
        pages.push(total);
        return pages;
    },

    /**
     * Pagine les éléments d'un conteneur (lignes de tableau ou cartes).
     * La barre reste masquée tant qu'il n'y a pas de quoi tourner la page.
     */
    paginer({ idConteneur, idBarre, selecteur = 'tr', taille = 10, libelle = 'lignes' }) {
        const conteneur = document.getElementById(idConteneur);
        const barre = document.getElementById(idBarre);
        if (!conteneur || !barre) return { rafraichir() {} };

        let page = 1;

        const eligibles = () => [...conteneur.querySelectorAll(selecteur)].filter(
            (element) => !element.classList.contains('line-nothing')
                && !element.classList.contains('grille-vide')
                && !element.classList.contains('filtre-masque')
        );

        const rendre = () => {
            const liste = eligibles();
            const pages = Math.max(1, Math.ceil(liste.length / taille));
            page = Math.min(page, pages);
            const debut = (page - 1) * taille;

            liste.forEach((element, index) => {
                element.classList.toggle(
                    'page-masquee', index < debut || index >= debut + taille
                );
            });

            if (liste.length <= taille) {
                barre.innerHTML = '';
                return;
            }

            const fin = Math.min(debut + taille, liste.length);
            barre.innerHTML = `
                <span class="pg-info">${debut + 1}–${fin} sur ${liste.length} ${libelle}</span>
                <span class="pg-divider"></span>
                <button class="pg-btn" data-page="${page - 1}" ${page === 1 ? 'disabled' : ''}
                        aria-label="Page précédente">‹</button>
                ${Divix._numerosPages(page, pages).map((numero) => numero === '…'
                    ? '<span class="pg-dots">…</span>'
                    : `<button class="pg-btn${numero === page ? ' active' : ''}" data-page="${numero}">${numero}</button>`
                ).join('')}
                <button class="pg-btn" data-page="${page + 1}" ${page === pages ? 'disabled' : ''}
                        aria-label="Page suivante">›</button>`;

            barre.querySelectorAll('.pg-btn[data-page]').forEach((bouton) => {
                bouton.addEventListener('click', () => {
                    page = Number(bouton.dataset.page);
                    rendre();
                });
            });
        };

        return {
            rafraichir(reinitialiser = false) {
                if (reinitialiser) page = 1;
                rendre();
            }
        };
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

/* Barre de navigation du téléphone : elle défile quand les onglets ne tiennent
   pas tous. On amène l'onglet courant sous les yeux et on signale, par un voile
   sur le bord, qu'il reste des onglets de ce côté. */
document.addEventListener('DOMContentLoaded', () => {
    const barre = document.querySelector('.navbar-mobile');
    const menu = barre?.querySelector('.menu');
    if (!menu) return;

    const marquerBords = () => {
        const reste = menu.scrollWidth - menu.clientWidth;
        barre.classList.toggle('reste-avant', menu.scrollLeft > 4);
        barre.classList.toggle('reste-apres', menu.scrollLeft < reste - 4);
    };

    const centrerOngletActif = () => {
        const actif = menu.querySelector('.nav-link.active');
        if (!actif) return;
        // scrollLeft plutôt que scrollIntoView : celui-ci ferait aussi sauter la page.
        menu.scrollLeft = actif.offsetLeft - (menu.clientWidth - actif.offsetWidth) / 2;
    };

    centrerOngletActif();
    marquerBords();
    menu.addEventListener('scroll', marquerBords, { passive: true });
    window.addEventListener('resize', () => {
        centrerOngletActif();
        marquerBords();
    });
});
