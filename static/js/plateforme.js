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
                <div class="d-flex gap-1">
                    <button class="btn btn-sm btn-outline-secondary ouvrir-modules"
                            data-id="${ets.id}" data-nom="${Divix.echapper(ets.nom)}">
                        Fonctionnalités
                    </button>
                    <button class="btn btn-sm ${ets.actif ? 'btn-outline-danger' : 'btn-outline-success'} bascule-etablissement"
                            data-id="${ets.id}" data-actif="${ets.actif ? '0' : '1'}"
                            data-nom="${Divix.echapper(ets.nom)}">
                        ${ets.actif ? 'Suspendre' : 'Rouvrir'}
                    </button>
                </div>
            </td>
        </tr>`).join('');

    document.querySelectorAll('.bascule-etablissement').forEach((bouton) => {
        bouton.addEventListener('click', () => basculer(bouton));
    });
    document.querySelectorAll('.ouvrir-modules').forEach((bouton) => {
        bouton.addEventListener('click', () => ouvrirModules(bouton.dataset));
    });

    appliquerFiltresPlateforme?.();
}

/* ------------------------------------------------------------------ */
/* Fonctionnalités d'un établissement                                  */
/* ------------------------------------------------------------------ */

async function ouvrirModules({ id, nom }) {
    document.getElementById('modulesEtablissement').textContent = nom;
    Divix.chargement('tbody-modules', 3);
    bootstrap.Modal.getOrCreateInstance(document.getElementById('modulesModal')).show();

    try {
        const reponse = await Divix.charger(`/plateforme/${id}/modules`);
        afficherModules(id, reponse.data || []);
    } catch (erreur) {
        console.error(erreur);
        Divix.vide('tbody-modules', 'Impossible de charger les fonctionnalités', 3);
    }
}

function afficherModules(id, modules) {
    document.getElementById('tbody-modules').innerHTML = modules.map((module) => `
        <tr>
            <td data-label="Fonctionnalité">
                <span class="fw-semibold">${Divix.echapper(module.libelle)}</span>
                ${module.obligatoire
                    ? '<span class="badge badge-success ms-1">Indispensable</span>'
                    : ''}
            </td>
            <td data-label="Description">
                <span class="small text-muted">${Divix.echapper(module.description)}</span>
            </td>
            <td data-label="État" class="text-center">
                <div class="form-check form-switch d-inline-block m-0">
                    <input class="form-check-input bascule-module" type="checkbox" role="switch"
                           data-cle="${module.cle}" ${module.actif ? 'checked' : ''}
                           ${module.obligatoire ? 'disabled' : ''}>
                </div>
            </td>
        </tr>`).join('');

    document.querySelectorAll('.bascule-module').forEach((interrupteur) => {
        interrupteur.addEventListener('change', () => basculerModule(id, interrupteur));
    });
}

async function basculerModule(id, interrupteur) {
    const actif = interrupteur.checked;
    interrupteur.disabled = true;

    try {
        const reponse = await Divix.envoyer(`/plateforme/${id}/modules`, {
            cle: interrupteur.dataset.cle,
            actif: actif ? '1' : '0'
        });
        if (!reponse.success) {
            // L'interrupteur revient où il était : il ne doit pas montrer un
            // état que la base n'a pas enregistré.
            interrupteur.checked = !actif;
            Divix.erreur(reponse.error || 'Modification impossible');
            return;
        }
        Divix.succes(reponse.message);
    } catch (erreur) {
        console.error(erreur);
        interrupteur.checked = !actif;
        Divix.erreur('Modification impossible');
    } finally {
        interrupteur.disabled = false;
    }
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
