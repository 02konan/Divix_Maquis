/* Plan de salle : état des tables et changement de statut. */

let tablesSalle = [];

async function chargerSalle() {
    const conteneur = document.getElementById('plan-salle');
    if (!Divix.silencieux()) {
        conteneur.innerHTML = '<p class="small text-muted m-0">Chargement du plan de salle...</p>';
    }

    try {
        const reponse = await Divix.charger('/salle/list');
        tablesSalle = reponse.data || [];
        Divix.compteurs(reponse.counter);
        afficherPlan();
    } catch (erreur) {
        console.error(erreur);
        conteneur.innerHTML = '<p class="small text-danger m-0">Impossible de charger le plan de salle</p>';
    }
}

function afficherPlan() {
    const conteneur = document.getElementById('plan-salle');
    const zoneFiltree = document.getElementById('filtreZone').value;
    const tables = zoneFiltree
        ? tablesSalle.filter((table) => table.zone === zoneFiltree)
        : tablesSalle;

    if (!tables.length) {
        conteneur.innerHTML = '<p class="small text-muted m-0">Aucune table dans cette zone</p>';
        return;
    }

    conteneur.innerHTML = tables.map((table) => `
        <div class="carte-table statut-${slug(table.statut)}">
            <div class="d-flex align-items-center">
                <span class="numero-table">${Divix.echapper(table.numero)}</span>
                <span class="ms-auto badge ${Divix.classeStatut(table.statut)}">${Divix.echapper(table.statut)}</span>
            </div>
            <p class="small text-muted m-0 mt-2">${Divix.echapper(table.zone)} · ${table.places} places</p>
            ${table.commande_en_cours ? `
                <div class="ticket-table mt-2">
                    <span class="small fw-medium">${Divix.echapper(table.commande_en_cours)}</span>
                    <span class="small text-muted d-block">${Divix.fcfa(table.montant_en_cours)} · depuis ${Divix.heure(table.ouverte_depuis)}</span>
                </div>` : ''}
            <div class="d-flex gap-2 mt-3">
                ${boutonStatut(table, 'Libre')}
                ${boutonStatut(table, 'Réservée')}
            </div>
        </div>
    `).join('');
}

function boutonStatut(table, statut) {
    const desactive = table.statut === statut
        || (statut === 'Libre' && table.commande_en_cours);
    return `
        <button class="btn btn-sm btn-outline-secondary flex-fill" ${desactive ? 'disabled' : ''}
                onclick="changerStatutTable(${table.id}, '${statut}')">
            ${statut}
        </button>`;
}

function slug(texte) {
    return String(texte)
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .toLowerCase();
}

async function changerStatutTable(idTable, statut) {
    try {
        const reponse = await Divix.envoyer(`/salle/${idTable}/statut`, { statut });
        if (reponse.success) {
            chargerSalle();
        } else {
            Divix.erreur(reponse.error);
        }
    } catch (erreur) {
        console.error(erreur);
        Divix.erreur("Impossible de mettre à jour la table");
    }
}

document.addEventListener('DOMContentLoaded', () => {
    chargerSalle();
    Divix.rafraichirRegulierement({ charger: chargerSalle, intervalle: 10000 });
    document.getElementById('filtreZone')?.addEventListener('change', afficherPlan);

    Divix.brancherFormulaire({
        idBouton: 'submitTableBtn',
        idFormulaire: 'tableForm',
        url: '/salle/add',
        idModal: 'tableModal',
        apres: chargerSalle
    });
});
