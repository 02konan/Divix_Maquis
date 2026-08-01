/* Carte du maquis : présentation en cartes-plats, disponibilité et création. */

let articlesMenu = [];
let categorieActive = '';
let modifiable = false;

const EMOJI_DEFAUT = { Bar: '🍺', Cuisine: '🍽️' };

function grille() {
    return document.getElementById('grille-menu');
}

async function chargerMenu() {
    grille().innerHTML = '<div class="squelette-plat"></div>'.repeat(8);

    try {
        const reponse = await Divix.charger('/menu/list');
        articlesMenu = reponse.data || [];
        Divix.compteurs(reponse.counter);
        afficherMenu();
    } catch (erreur) {
        console.error(erreur);
        grille().innerHTML = '<p class="grille-vide">Impossible de charger la carte</p>';
    }
}

function pastilleStock(article) {
    if (!article.gere_stock) return '';
    const classe = article.stock <= 0
        ? 'badge-danger'
        : (article.stock <= article.seuil_alerte ? 'badge-pending' : 'badge-success');
    return `<span class="pastille-stock badge ${classe}">${article.stock} en stock</span>`;
}

function carteArticle(article) {
    const marge = article.prix - article.cout_revient;
    const pourcentage = article.prix > 0 ? Math.round((marge / article.prix) * 100) : 0;
    const indisponible = !article.disponible || (article.gere_stock && article.stock <= 0);

    const visuel = article.image
        ? `<img src="/static/uploads/${Divix.echapper(article.image)}" alt="${Divix.echapper(article.nom)}" loading="lazy">`
        : (EMOJI_DEFAUT[article.type_categorie] || '🍽️');

    const action = modifiable
        ? `<button class="btn btn-sm ms-auto ${article.disponible ? 'btn-action-annuler' : 'btn-action-servir'}"
                   onclick="basculerDisponibilite(${article.id}, ${article.disponible ? 0 : 1})">
               ${article.disponible ? 'Retirer' : 'Remettre'}
           </button>`
        : '';

    return `
    <article class="carte-plat ${indisponible ? 'indisponible' : ''}"
             data-categorie="${Divix.echapper(article.categorie)}"
             data-recherche="${Divix.echapper(`${article.nom} ${article.categorie} ${article.reference}`).toLowerCase()}">
        <div class="photo-plat">
            ${visuel}
            <span class="etiquette-categorie">${Divix.echapper(article.categorie)}</span>
            ${pastilleStock(article)}
            ${indisponible ? `<span class="voile-indisponible">${article.disponible ? 'Rupture' : 'Hors carte'}</span>` : ''}
        </div>
        <div class="corps-plat">
            <h3 class="nom-plat">${Divix.echapper(article.nom)}</h3>
            <span class="small text-muted">
                ${article.cout_revient > 0
                    ? `Marge ${Divix.fcfa(marge)} · ${pourcentage}%`
                    : Divix.echapper(article.reference)}
            </span>
            <div class="pied-plat">
                <span class="prix-plat">${Divix.fcfa(article.prix)}</span>
                ${action}
            </div>
        </div>
    </article>`;
}

function afficherMenu() {
    if (!articlesMenu.length) {
        grille().innerHTML = '<p class="grille-vide">Aucun article au menu</p>';
        return;
    }

    grille().innerHTML = articlesMenu.map(carteArticle).join('');
    filtrerCartes();
}

function filtrerCartes() {
    const recherche = (document.getElementById('searchInput')?.value || '')
        .toLowerCase()
        .trim();

    let visibles = 0;
    grille().querySelectorAll('.carte-plat').forEach((carte) => {
        const correspond =
            (!categorieActive || carte.dataset.categorie === categorieActive) &&
            (!recherche || carte.dataset.recherche.includes(recherche));
        carte.style.display = correspond ? '' : 'none';
        if (correspond) visibles += 1;
    });

    const message = grille().querySelector('.grille-vide');
    if (!visibles && !message) {
        grille().insertAdjacentHTML('beforeend', '<p class="grille-vide">Aucun article ne correspond</p>');
    } else if (visibles && message) {
        message.remove();
    }
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
    modifiable = grille()?.dataset.modifiable === '1';
    chargerMenu();

    document.getElementById('searchInput')?.addEventListener('input', filtrerCartes);

    document.querySelectorAll('.chip-categorie').forEach((chip) => {
        chip.addEventListener('click', () => {
            document.querySelectorAll('.chip-categorie').forEach((autre) => {
                autre.classList.toggle('actif', autre === chip);
            });
            categorieActive = chip.dataset.categorie;
            filtrerCartes();
        });
    });

    // Le bloc stock ne concerne que les articles décomptés (boissons).
    const selecteurStock = document.getElementById('articleGereStock');
    const blocStock = document.getElementById('blocStock');
    selecteurStock?.addEventListener('change', () => {
        blocStock.style.display = selecteurStock.value === '1' ? '' : 'none';
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
