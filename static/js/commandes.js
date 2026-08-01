/* Prise de commande, suivi des tickets et détail imprimable. */

let catalogue = [];        // articles disponibles à la commande
let panier = [];           // { id_article, nom, prix, quantite }
let commandes = [];        // historique affiché dans le tableau
let referenceAffichee = null;

/* -------------------------------------------------------------------------- */
/* Catalogue et panier                                                        */
/* -------------------------------------------------------------------------- */

async function chargerCatalogue() {
    const bouton = document.getElementById('submitCommandeBtn');
    const texte = document.getElementById('submitCommandeBtnText');

    try {
        const reponse = await Divix.charger('/menu/disponibles');
        catalogue = reponse.data || [];
        texte.textContent = 'Enregistrer la commande';
        bouton.disabled = false;
    } catch (erreur) {
        console.error(erreur);
        texte.textContent = 'Menu indisponible';
    }
}

function brancherRecherche() {
    const champ = document.getElementById('articleSearch');
    const liste = document.getElementById('articleDropdown');
    if (!champ || !liste) return;

    const afficherSuggestions = () => {
        const terme = champ.value.toLowerCase().trim();
        const resultats = catalogue
            .filter((article) => article.nom.toLowerCase().includes(terme)
                || article.categorie.toLowerCase().includes(terme))
            .slice(0, 20);

        if (!resultats.length) {
            liste.style.display = 'none';
            return;
        }

        liste.innerHTML = resultats.map((article) => `
            <li class="list-group-item list-group-item-action d-flex align-items-center"
                style="cursor:pointer" onclick="ajouterAuPanier(${article.id})">
                <span>${Divix.echapper(article.nom)}
                    <span class="small text-muted">· ${Divix.echapper(article.categorie)}</span>
                </span>
                <span class="ms-auto small fw-medium">${Divix.fcfa(article.prix)}</span>
            </li>`).join('');
        liste.style.display = 'block';
    };

    champ.addEventListener('input', afficherSuggestions);
    champ.addEventListener('focus', afficherSuggestions);

    document.addEventListener('click', (evenement) => {
        if (!champ.contains(evenement.target) && !liste.contains(evenement.target)) {
            liste.style.display = 'none';
        }
    });
}

function ajouterAuPanier(idArticle) {
    const article = catalogue.find((element) => element.id === idArticle);
    if (!article) return;

    const existant = panier.find((ligne) => ligne.id_article === idArticle);
    if (existant) {
        existant.quantite += 1;
    } else {
        panier.push({
            id_article: article.id,
            nom: article.nom,
            prix: article.prix,
            quantite: 1
        });
    }

    document.getElementById('articleSearch').value = '';
    document.getElementById('articleDropdown').style.display = 'none';
    afficherPanier();
}

function modifierQuantite(idArticle, delta) {
    const ligne = panier.find((element) => element.id_article === idArticle);
    if (!ligne) return;

    ligne.quantite += delta;
    if (ligne.quantite <= 0) {
        panier = panier.filter((element) => element.id_article !== idArticle);
    }
    afficherPanier();
}

function afficherPanier() {
    const conteneur = document.getElementById('selectedArticlesTags');

    if (!panier.length) {
        conteneur.innerHTML = '<span class="small text-muted">Aucun article sélectionné</span>';
    } else {
        conteneur.innerHTML = panier.map((ligne) => `
            <div class="ligne-panier d-flex align-items-center gap-2">
                <span class="flex-fill">${Divix.echapper(ligne.nom)}</span>
                <span class="small text-muted">${Divix.fcfa(ligne.prix)}</span>
                <div class="btn-group btn-group-sm">
                    <button type="button" class="btn btn-outline-secondary"
                            onclick="modifierQuantite(${ligne.id_article}, -1)">−</button>
                    <span class="btn btn-outline-secondary disabled">${ligne.quantite}</span>
                    <button type="button" class="btn btn-outline-secondary"
                            onclick="modifierQuantite(${ligne.id_article}, 1)">+</button>
                </div>
                <span class="fw-medium" style="min-width:90px; text-align:right;">
                    ${Divix.fcfa(ligne.prix * ligne.quantite)}
                </span>
            </div>`).join('');
    }

    recalculerTotal();
}

function recalculerTotal() {
    const sousTotal = panier.reduce((somme, ligne) => somme + ligne.prix * ligne.quantite, 0);
    const remise = Number(document.getElementById('remise').value) || 0;
    const net = Math.max(sousTotal - remise, 0);

    document.getElementById('sousTotal').value = Divix.fcfa(sousTotal);
    document.getElementById('totalCommande').value = Divix.fcfa(net);
    document.getElementById('articlesHidden').value = JSON.stringify(
        panier.map(({ id_article, quantite }) => ({ id_article, quantite }))
    );
}

/* -------------------------------------------------------------------------- */
/* Historique                                                                 */
/* -------------------------------------------------------------------------- */

async function chargerCommandes() {
    Divix.chargement('tbody-commandes', 9);

    try {
        const reponse = await Divix.charger('/commande/list');
        commandes = reponse.data || [];
        Divix.compteurs(reponse.counter);
        afficherCommandes();
    } catch (erreur) {
        console.error(erreur);
        Divix.vide('tbody-commandes', 'Impossible de charger les commandes', 9);
    }
}

function afficherCommandes() {
    if (!commandes.length) {
        Divix.vide('tbody-commandes', 'Aucune commande enregistrée', 9);
        return;
    }

    document.getElementById('tbody-commandes').innerHTML = commandes.map((commande) => `
        <tr data-statut="${Divix.echapper(commande.statut)}">
            <td data-label="Référence"><span class="text-muted small">${Divix.echapper(commande.reference)}</span></td>
            <td data-label="Table">${Divix.echapper(commande.table_numero)}</td>
            <td data-label="Client">${Divix.echapper(commande.nom_client || 'Client comptoir')}</td>
            <td data-label="Articles"><span class="small text-muted">${Divix.echapper(commande.articles || '—')}</span></td>
            <td data-label="Montant">${Divix.fcfa(commande.montant_total)}</td>
            <td data-label="Reste">${commande.reste_a_payer > 0
                ? `<span class="text-danger fw-medium">${Divix.fcfa(commande.reste_a_payer)}</span>`
                : '<span class="text-muted">—</span>'}</td>
            <td data-label="Statut">${Divix.badge(commande.statut)}</td>
            <td data-label="Date"><span class="text-muted small">${Divix.date(commande.date_commande, true)}</span></td>
            <td class="no-print-col" data-label="Action" style="text-align:end;">
                <div style="display:flex; gap:6px; justify-content:flex-end;">
                    <button class="btn btn-sm btn-action-voir" onclick="voirCommande('${commande.reference}')" title="Détail">
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5m0 12a4.5 4.5 0 1 1 0-9 4.5 4.5 0 0 1 0 9"/>
                        </svg>
                    </button>
                    ${commande.statut === 'En cours' ? `
                    <button class="btn btn-sm btn-action-servir" onclick="marquerStatut('${commande.reference}', 'Servie')" title="Marquer servie">
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
                            <path d="m9.71 17.71 9-9-1.42-1.42L9.71 14.88 6.71 11.88l-1.42 1.42z"/>
                        </svg>
                    </button>` : ''}
                    ${['En cours', 'Servie'].includes(commande.statut) ? `
                    <button class="btn btn-sm btn-action-annuler" onclick="annulerCommande('${commande.reference}')" title="Annuler">
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
                        </svg>
                    </button>` : ''}
                </div>
            </td>
        </tr>`).join('');

    appliquerFiltres?.();
}

/* -------------------------------------------------------------------------- */
/* Actions                                                                    */
/* -------------------------------------------------------------------------- */

async function marquerStatut(reference, statut) {
    try {
        const reponse = await Divix.envoyer(`/commande/${reference}/statut`, { statut });
        if (reponse.success) {
            chargerCommandes();
        } else {
            Divix.erreur(reponse.error);
        }
    } catch (erreur) {
        console.error(erreur);
        Divix.erreur("Impossible de mettre à jour la commande");
    }
}

async function annulerCommande(reference) {
    const confirmation = await Swal.fire({
        icon: 'warning',
        title: 'Annuler cette commande ?',
        text: `La commande ${reference} sera marquée comme annulée.`,
        showCancelButton: true,
        confirmButtonText: 'Oui, annuler',
        cancelButtonText: 'Retour',
        confirmButtonColor: '#d33'
    });

    if (confirmation.isConfirmed) marquerStatut(reference, 'Annulée');
}

async function voirCommande(reference) {
    const corps = document.getElementById('detailBody');
    corps.innerHTML = '<p class="small text-muted m-0">Chargement...</p>';
    referenceAffichee = reference;
    bootstrap.Modal.getOrCreateInstance(document.getElementById('detailModal')).show();

    try {
        const reponse = await Divix.charger(`/commande/${reference}`);
        if (!reponse.success) throw new Error(reponse.error);
        afficherDetail(reponse.data);
    } catch (erreur) {
        console.error(erreur);
        corps.innerHTML = '<p class="small text-danger m-0">Commande introuvable</p>';
    }
}

function afficherDetail(commande) {
    document.getElementById('detailTitre').textContent = commande.reference;
    document.getElementById('detailSousTitre').textContent =
        `Table ${commande.table_numero} · ${commande.type_service} · ${Divix.date(commande.date_commande, true)}`;

    const lignes = commande.lignes.map((ligne) => `
        <tr>
            <td>${Divix.echapper(ligne.article)}</td>
            <td class="text-center">${ligne.quantite}</td>
            <td class="text-end">${Divix.fcfa(ligne.prix_unitaire)}</td>
            <td class="text-end fw-medium">${Divix.fcfa(ligne.total)}</td>
        </tr>`).join('');

    const paiements = commande.paiements.length
        ? commande.paiements.map((paiement) => `
            <div class="d-flex small">
                <span>${Divix.echapper(paiement.mode)} · ${Divix.date(paiement.date_paiement, true)}</span>
                <span class="ms-auto fw-medium">${Divix.fcfa(paiement.montant)}</span>
            </div>`).join('')
        : '<p class="small text-muted m-0">Aucun encaissement</p>';

    document.getElementById('detailBody').innerHTML = `
        <div class="d-flex align-items-center mb-3">
            <div>
                <p class="m-0 fw-medium">${Divix.echapper(commande.nom_client || 'Client comptoir')}</p>
                <span class="small text-muted">${commande.couverts} couvert(s) · servi par ${Divix.echapper(commande.serveur)}</span>
            </div>
            <span class="ms-auto">${Divix.badge(commande.statut)}</span>
        </div>
        <table class="table table-sm align-middle">
            <thead><tr class="table-light">
                <th class="text-muted">ARTICLE</th>
                <th class="text-muted text-center">QTÉ</th>
                <th class="text-muted text-end">P.U.</th>
                <th class="text-muted text-end">TOTAL</th>
            </tr></thead>
            <tbody>${lignes}</tbody>
        </table>
        <div class="recap-addition">
            ${commande.remise > 0 ? `<div class="d-flex small"><span>Remise</span><span class="ms-auto">− ${Divix.fcfa(commande.remise)}</span></div>` : ''}
            <div class="d-flex"><span class="fw-medium">Net à payer</span><span class="ms-auto fw-semibold">${Divix.fcfa(commande.montant_total)}</span></div>
            <div class="d-flex small"><span>Déjà encaissé</span><span class="ms-auto">${Divix.fcfa(commande.total_paye)}</span></div>
            <div class="d-flex small"><span>Reste à payer</span><span class="ms-auto ${commande.reste_a_payer > 0 ? 'text-danger fw-medium' : ''}">${Divix.fcfa(commande.reste_a_payer)}</span></div>
        </div>
        ${commande.commentaire ? `<p class="small text-muted mt-3 mb-0">Note : ${Divix.echapper(commande.commentaire)}</p>` : ''}
        <hr>
        <p class="small text-muted mb-2">Encaissements</p>
        ${paiements}`;
}

function imprimerTicket() {
    if (!referenceAffichee) return;

    const contenu = document.getElementById('detailBody').innerHTML;
    const fenetre = window.open('', '_blank', 'width=420,height=640');
    fenetre.document.write(`
        <html>
        <head>
            <title>Ticket ${referenceAffichee}</title>
            <style>
                * { box-sizing: border-box; }
                body { font-family: Arial, sans-serif; padding: 20px; font-size: 13px; color: #222; }
                h2 { font-size: 18px; margin: 0 0 4px; }
                table { width: 100%; border-collapse: collapse; margin-top: 12px; }
                th { text-align: left; font-size: 11px; color: #666; text-transform: uppercase; padding: 6px 0; border-bottom: 1px solid #eee; }
                td { padding: 6px 0; border-bottom: 1px solid #f4f4f4; }
                .text-end { text-align: right; }
                .text-center { text-align: center; }
                .recap-addition { margin-top: 12px; border-top: 1px dashed #bbb; padding-top: 10px; }
                .recap-addition > div { display: flex; margin-bottom: 4px; }
                .ms-auto { margin-left: auto; }
                .badge { display: inline-block; padding: 3px 10px; border-radius: 20px; background: #eee; font-size: 11px; }
                .pied { margin-top: 24px; text-align: center; font-size: 11px; color: #999; }
            </style>
        </head>
        <body>
            <h2>Divix Maquis</h2>
            <p style="margin:0;color:#888;">Ticket ${referenceAffichee}</p>
            ${contenu}
            <p class="pied">Merci de votre visite — à bientôt !</p>
        </body>
        </html>`);
    fenetre.document.close();
    fenetre.focus();
    fenetre.print();
    fenetre.close();
}

/* -------------------------------------------------------------------------- */

let appliquerFiltres = null;
let paginationCommandes = null;

/* Panier éventuellement constitué depuis la carte (bouton « Ajouter »). */
function reprendrePanierDeLaCarte() {
    try {
        const enAttente = JSON.parse(sessionStorage.getItem('divix.panier')) || [];
        if (!enAttente.length) return;
        panier = enAttente;
        sessionStorage.removeItem('divix.panier');
        afficherPanier();
    } catch (erreur) {
        console.error(erreur);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    chargerCatalogue();
    chargerCommandes();
    brancherRecherche();
    afficherPanier();

    document.getElementById('remise')?.addEventListener('input', recalculerTotal);
    document.getElementById('imprimerTicketBtn')?.addEventListener('click', imprimerTicket);

    paginationCommandes = Divix.paginer({
        idConteneur: 'tbody-commandes',
        idBarre: 'pagination-commandes',
        taille: 10,
        libelle: 'commandes'
    });

    appliquerFiltres = Divix.brancherFiltres({
        idTbody: 'tbody-commandes',
        idRecherche: 'searchInput',
        filtres: [{ idSelect: 'filtreStatut', attribut: 'statut' }],
        apres: () => paginationCommandes.rafraichir(true)
    });

    reprendrePanierDeLaCarte();

    Divix.brancherFormulaire({
        idBouton: 'submitCommandeBtn',
        idFormulaire: 'commandeForm',
        url: '/commande/add',
        idModal: 'commandeModal',
        avantEnvoi: () => {
            if (!panier.length) {
                Divix.erreur('Ajoutez au moins un article à la commande');
                return false;
            }
            return true;
        },
        apres: () => {
            panier = [];
            afficherPanier();
            chargerCommandes();
            chargerCatalogue();
        }
    });
});
