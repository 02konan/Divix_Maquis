/* Caisse : encaissements, journal et répartition par mode de paiement. */

let commandesEncaissables = [];
let appliquerFiltresCaisse = null;

async function chargerCaisse() {
    Divix.chargement('tbody-caisse', 8);

    try {
        const reponse = await Divix.charger('/caisse/list');
        Divix.compteurs(reponse.counter);
        afficherJournal(reponse.data || []);
        afficherModes(reponse.modes || []);
    } catch (erreur) {
        console.error(erreur);
        Divix.vide('tbody-caisse', 'Impossible de charger le journal de caisse', 8);
    }
}

function afficherJournal(paiements) {
    if (!paiements.length) {
        Divix.vide('tbody-caisse', 'Aucun encaissement enregistré', 8);
        return;
    }

    document.getElementById('tbody-caisse').innerHTML = paiements.map((paiement) => `
        <tr data-mode="${Divix.echapper(paiement.mode)}">
            <td data-label="Reçu"><span class="text-muted small">${Divix.echapper(paiement.reference)}</span></td>
            <td data-label="Commande">${Divix.echapper(paiement.commande)}</td>
            <td data-label="Table">${Divix.echapper(paiement.table_numero)}</td>
            <td data-label="Client">${Divix.echapper(paiement.nom_client || 'Client comptoir')}</td>
            <td data-label="Montant"><span class="fw-medium">${Divix.fcfa(paiement.montant)}</span></td>
            <td data-label="Mode">${Divix.badge(paiement.mode)}</td>
            <td data-label="Caissier">${Divix.echapper(paiement.caissier)}</td>
            <td data-label="Date"><span class="text-muted small">${Divix.date(paiement.date_paiement, true)}</span></td>
        </tr>`).join('');

    appliquerFiltresCaisse?.();
}

function afficherModes(modes) {
    const conteneur = document.getElementById('modes-paiement');
    if (!conteneur) return;

    if (!modes.length) {
        conteneur.innerHTML = '<span class="small text-muted">Aucun encaissement aujourd\'hui</span>';
        return;
    }

    const total = modes.reduce((somme, mode) => somme + mode.total, 0);

    conteneur.innerHTML = modes.map((mode) => `
        <div class="carte-mode">
            <span class="small text-muted">${Divix.echapper(mode.mode)}</span>
            <p class="m-0 fw-semibold">${Divix.fcfa(mode.total)}</p>
            <span class="small text-muted">${mode.nombre} opération(s) · ${Math.round((mode.total / total) * 100)}%</span>
        </div>`).join('');
}

async function chargerEncaissables() {
    const selecteur = document.getElementById('referenceCommande');

    try {
        const reponse = await Divix.charger('/caisse/encaissables');
        commandesEncaissables = reponse.data || [];

        if (!commandesEncaissables.length) {
            selecteur.innerHTML = '<option value="" disabled selected>Aucune commande à encaisser</option>';
            return;
        }

        selecteur.innerHTML = '<option value="" disabled selected>--choisir--</option>'
            + commandesEncaissables.map((commande) => `
                <option value="${commande.reference}">
                    ${commande.reference} · Table ${commande.table_numero} · ${Divix.fcfa(commande.reste_a_payer)}
                </option>`).join('');
    } catch (erreur) {
        console.error(erreur);
        selecteur.innerHTML = '<option value="" disabled selected>Erreur de chargement</option>';
    }
}

function surSelectionCommande() {
    const reference = document.getElementById('referenceCommande').value;
    const commande = commandesEncaissables.find((element) => element.reference === reference);
    if (!commande) return;

    document.getElementById('resteAPayer').value = Divix.fcfa(commande.reste_a_payer);
    const champMontant = document.getElementById('montantEncaisse');
    champMontant.value = commande.reste_a_payer;
    champMontant.max = commande.reste_a_payer;
}

document.addEventListener('DOMContentLoaded', () => {
    chargerCaisse();
    chargerEncaissables();

    document.getElementById('referenceCommande')
        ?.addEventListener('change', surSelectionCommande);

    appliquerFiltresCaisse = Divix.brancherFiltres({
        idTbody: 'tbody-caisse',
        idRecherche: 'searchInput',
        filtres: [{ idSelect: 'filtreMode', attribut: 'mode' }]
    });

    Divix.brancherFormulaire({
        idBouton: 'submitEncaissementBtn',
        idFormulaire: 'encaissementForm',
        url: '/caisse/add',
        idModal: 'encaissementModal',
        apres: () => {
            document.getElementById('resteAPayer').value = '0 FCFA';
            chargerCaisse();
            chargerEncaissables();
        }
    });
});
