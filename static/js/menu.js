/* Carte du maquis : liste des articles, disponibilité et création. */

let articlesMenu = [];
let appliquerFiltresMenu = null;

async function chargerMenu() {
    Divix.chargement('tbody-menu', 8);

    try {
        const reponse = await Divix.charger('/menu/list');
        articlesMenu = reponse.data || [];
        Divix.compteurs(reponse.counter);
        afficherMenu();
    } catch (erreur) {
        console.error(erreur);
        Divix.vide('tbody-menu', 'Impossible de charger la carte', 8);
    }
}

function afficherMenu() {
    if (!articlesMenu.length) {
        Divix.vide('tbody-menu', 'Aucun article au menu', 8);
        return;
    }

    document.getElementById('tbody-menu').innerHTML = articlesMenu.map((article) => {
        const marge = article.prix - article.cout_revient;
        const pourcentageMarge = article.prix > 0
            ? Math.round((marge / article.prix) * 100)
            : 0;

        return `
        <tr data-categorie="${Divix.echapper(article.categorie)}">
            <td data-label="Référence"><span class="text-muted small">${Divix.echapper(article.reference)}</span></td>
            <td data-label="Article">
                <div class="d-flex align-items-center gap-2">
                    <div class="vignette-article">
                        ${article.image
                            ? `<img src="/static/uploads/${Divix.echapper(article.image)}" alt="">`
                            : (article.type_categorie === 'Bar' ? '🍺' : '🍽️')}
                    </div>
                    <div>
                        <p class="m-0 p-0">${Divix.echapper(article.nom)}</p>
                        ${article.disponible ? '' : '<span class="small text-danger">Retiré de la carte</span>'}
                    </div>
                </div>
            </td>
            <td data-label="Catégorie">${Divix.echapper(article.categorie)}</td>
            <td data-label="Prix">${Divix.fcfa(article.prix)}</td>
            <td data-label="Marge">
                ${article.cout_revient > 0
                    ? `${Divix.fcfa(marge)} <span class="small text-muted">(${pourcentageMarge}%)</span>`
                    : '<span class="text-muted">—</span>'}
            </td>
            <td data-label="Stock">${article.gere_stock ? article.stock : '<span class="text-muted">—</span>'}</td>
            <td data-label="Statut">${Divix.badge(article.statut)}</td>
            <td class="no-print-col" data-label="Action" style="text-align:end;">
                <div style="display:flex; gap:6px; justify-content:flex-end;">
                    <button class="btn btn-sm ${article.disponible ? 'btn-action-annuler' : 'btn-action-servir'}"
                            onclick="basculerDisponibilite(${article.id}, ${article.disponible ? 0 : 1})"
                            title="${article.disponible ? 'Retirer de la carte' : 'Remettre à la carte'}">
                        ${article.disponible ? 'Retirer' : 'Remettre'}
                    </button>
                </div>
            </td>
        </tr>`;
    }).join('');

    appliquerFiltresMenu?.();
}

async function basculerDisponibilite(idArticle, disponible) {
    try {
        const reponse = await Divix.envoyer(`/menu/${idArticle}/disponibilite`, { disponible });
        if (reponse.success) {
            chargerMenu();
        } else {
            Divix.erreur(reponse.error);
        }
    } catch (erreur) {
        console.error(erreur);
        Divix.erreur("Impossible de modifier la disponibilité");
    }
}

document.addEventListener('DOMContentLoaded', () => {
    chargerMenu();

    // Le bloc stock ne concerne que les articles décomptés (boissons).
    const selecteurStock = document.getElementById('articleGereStock');
    const blocStock = document.getElementById('blocStock');
    selecteurStock?.addEventListener('change', () => {
        blocStock.style.display = selecteurStock.value === '1' ? '' : 'none';
    });

    appliquerFiltresMenu = Divix.brancherFiltres({
        idTbody: 'tbody-menu',
        idRecherche: 'searchInput',
        filtres: [{ idSelect: 'filtreCategorie', attribut: 'categorie' }]
    });

    Divix.brancherFormulaire({
        idBouton: 'submitArticleBtn',
        idFormulaire: 'articleForm',
        url: '/menu/add',
        idModal: 'articleModal',
        apres: () => {
            blocStock.style.display = 'none';
            chargerMenu();
        }
    });

    Divix.brancherFormulaire({
        idBouton: 'submitCategorieBtn',
        idFormulaire: 'categorieForm',
        url: '/menu/categorie/add',
        idModal: 'categorieModal',
        apres: () => window.location.reload()
    });
});
