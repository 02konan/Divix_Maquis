/* Journal des dépenses du maquis. */

let appliquerFiltresDepenses = null;

async function chargerDepenses() {
    Divix.chargement('tbody-depenses', 7);

    try {
        const reponse = await Divix.charger('/depense/list');
        Divix.compteurs(reponse.counter);
        afficherDepenses(reponse.data || []);
    } catch (erreur) {
        console.error(erreur);
        Divix.vide('tbody-depenses', 'Impossible de charger les dépenses', 7);
    }
}

function afficherDepenses(depenses) {
    if (!depenses.length) {
        Divix.vide('tbody-depenses', 'Aucune dépense enregistrée', 7);
        return;
    }

    document.getElementById('tbody-depenses').innerHTML = depenses.map((depense) => `
        <tr data-categorie="${Divix.echapper(depense.categorie)}">
            <td data-label="Référence"><span class="text-muted small">${Divix.echapper(depense.reference)}</span></td>
            <td data-label="Libellé">${Divix.echapper(depense.libelle)}</td>
            <td data-label="Catégorie"><span class="badge badge-pending">${Divix.echapper(depense.categorie)}</span></td>
            <td data-label="Fournisseur">${Divix.echapper(depense.fournisseur || '—')}</td>
            <td data-label="Montant"><span class="fw-medium">${Divix.fcfa(depense.montant)}</span></td>
            <td data-label="Mode">${Divix.echapper(depense.mode_paiement || '—')}</td>
            <td data-label="Date"><span class="text-muted small">${Divix.date(depense.date_depense)}</span></td>
        </tr>`).join('');

    appliquerFiltresDepenses?.();
}

document.addEventListener('DOMContentLoaded', () => {
    chargerDepenses();

    appliquerFiltresDepenses = Divix.brancherFiltres({
        idTbody: 'tbody-depenses',
        idRecherche: 'searchInput',
        filtres: [{ idSelect: 'filtreCategorie', attribut: 'categorie' }]
    });

    Divix.brancherFormulaire({
        idBouton: 'submitDepenseBtn',
        idFormulaire: 'depenseForm',
        url: '/depense/add',
        idModal: 'depenseModal',
        apres: chargerDepenses
    });
});
