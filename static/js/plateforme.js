/* Console de l'éditeur : les établissements hébergés sur la plateforme. */

let appliquerFiltresPlateforme = null;
let paginationPlateforme = null;

async function chargerEtablissements() {
    Divix.chargement('tbody-plateforme', 8);

    try {
        const reponse = await Divix.charger('/plateforme/list');
        Divix.compteurs(reponse.counter);
        afficherEtablissements(reponse.data || []);
    } catch (erreur) {
        console.error(erreur);
        Divix.vide('tbody-plateforme', 'Impossible de charger les établissements', 8);
    }
}

function afficherEtablissements(etablissements) {
    if (!etablissements.length) {
        Divix.vide('tbody-plateforme', 'Aucun établissement', 8);
        return;
    }

    document.getElementById('tbody-plateforme').innerHTML = etablissements.map((ets) => `
        <tr data-etat="${ets.actif ? '1' : '0'}">
            <td data-label="Établissement"><span class="fw-medium">${Divix.echapper(ets.nom)}</span></td>
            <td data-label="Ville">${Divix.echapper(ets.ville || '—')}</td>
            <td data-label="Téléphone"><span class="text-muted small">${Divix.echapper(ets.telephone || '—')}</span></td>
            <td data-label="Comptes">${ets.comptes}</td>
            <td data-label="Commandes">${ets.commandes}</td>
            <td data-label="Encaissé">${Divix.fcfa(ets.encaisse)}</td>
            <td data-label="État">
                <span class="badge ${ets.actif ? 'badge-success' : 'badge-danger'}">
                    ${ets.actif ? 'En service' : 'Suspendu'}
                </span>
            </td>
            <td data-label="Action">
                <button class="btn btn-sm ${ets.actif ? 'btn-outline-danger' : 'btn-outline-success'} bascule-etablissement"
                        data-id="${ets.id}" data-actif="${ets.actif ? '0' : '1'}"
                        data-nom="${Divix.echapper(ets.nom)}">
                    ${ets.actif ? 'Suspendre' : 'Rouvrir'}
                </button>
            </td>
        </tr>`).join('');

    document.querySelectorAll('.bascule-etablissement').forEach((bouton) => {
        bouton.addEventListener('click', () => basculer(bouton));
    });

    appliquerFiltresPlateforme?.();
}

async function basculer(bouton) {
    const suspend = bouton.dataset.actif === '0';
    if (suspend) {
        // Suspendre ferme la porte à tout le personnel de l'établissement :
        // cela mérite une confirmation, pas un clic distrait.
        const choix = await Swal.fire({
            title: `Suspendre ${bouton.dataset.nom} ?`,
            text: "Personne ne pourra plus s'y connecter. Les données sont conservées.",
            icon: 'warning',
            showCancelButton: true,
            cancelButtonText: 'Annuler',
            confirmButtonText: 'Suspendre',
            confirmButtonColor: '#dc3545'
        });
        if (!choix.isConfirmed) return;
    }

    try {
        const reponse = await Divix.envoyer(`/plateforme/${bouton.dataset.id}/actif`, {
            actif: bouton.dataset.actif
        });
        if (!reponse.success) {
            Divix.erreur(reponse.error || 'Modification impossible');
            return;
        }
        await Divix.succes(reponse.message);
        chargerEtablissements();
    } catch (erreur) {
        console.error(erreur);
        Divix.erreur('Modification impossible');
    }
}

document.addEventListener('DOMContentLoaded', () => {
    chargerEtablissements();

    paginationPlateforme = Divix.paginer({
        idConteneur: 'tbody-plateforme',
        idBarre: 'pagination-plateforme',
        taille: 10,
        libelle: 'établissements'
    });

    appliquerFiltresPlateforme = Divix.brancherFiltres({
        idTbody: 'tbody-plateforme',
        idRecherche: 'searchInput',
        filtres: [{ idSelect: 'filtreEtat', attribut: 'etat' }],
        apres: () => paginationPlateforme.rafraichir(true)
    });

    Divix.rafraichirRegulierement({
        charger: chargerEtablissements,
        intervalle: 60000,
        pagination: paginationPlateforme
    });

    Divix.brancherFormulaire({
        idBouton: 'submitEtablissementBtn',
        idFormulaire: 'etablissementForm',
        url: '/plateforme/add',
        idModal: 'etablissementModal',
        apres: chargerEtablissements
    });
});
