/* Journal des actions : ce que chacun a fait dans l'établissement. */

let appliquerFiltresJournal = null;
let paginationJournal = null;

async function chargerJournal() {
    Divix.chargement('tbody-journal', 6);

    try {
        const reponse = await Divix.charger('/journal/list');
        Divix.compteurs(reponse.counter);
        afficherJournal(reponse.data || []);
    } catch (erreur) {
        console.error(erreur);
        Divix.vide('tbody-journal', 'Impossible de charger le journal', 6);
    }
}

function afficherJournal(actions) {
    if (!actions.length) {
        Divix.vide('tbody-journal', 'Aucune action enregistrée', 6);
        return;
    }

    document.getElementById('tbody-journal').innerHTML = actions.map((action) => `
        <tr data-libelle="${Divix.echapper(action.libelle)}">
            <td data-label="Date"><span class="text-muted small">${Divix.date(action.date_action, true)}</span></td>
            <td data-label="Auteur"><span class="fw-medium">${Divix.echapper(action.nom_utilisateur)}</span></td>
            <td data-label="Rôle"><span class="badge badge-pending">${Divix.echapper(action.role_utilisateur)}</span></td>
            <td data-label="Action">${Divix.echapper(action.libelle)}</td>
            <td data-label="Cible"><span class="text-muted small">${Divix.echapper(action.cible || '—')}</span></td>
            <td data-label="Détail"><span class="text-muted small">${Divix.echapper(action.details || '—')}</span></td>
        </tr>`).join('');

    appliquerFiltresJournal?.();
}

document.addEventListener('DOMContentLoaded', () => {
    chargerJournal();

    paginationJournal = Divix.paginer({
        idConteneur: 'tbody-journal',
        idBarre: 'pagination-journal',
        taille: 15,
        libelle: 'actions'
    });

    appliquerFiltresJournal = Divix.brancherFiltres({
        idTbody: 'tbody-journal',
        idRecherche: 'searchInput',
        filtres: [{ idSelect: 'filtreLibelle', attribut: 'libelle' }],
        apres: () => paginationJournal.rafraichir(true)
    });
});
