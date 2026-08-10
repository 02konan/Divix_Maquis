/* Carte en cartes-plats : partagée par les pages Maquis (boissons) et Menu
   (nourriture). L'URL de base vient du gabarit, tout le reste en découle. */

let articlesMenu = [];
let categorieActive = '';
let modifiable = false;
let commandable = false;
let paginationMenu = null;
let base = '/menu';

/* Panier constitué depuis la carte, repris tel quel par la page Commandes. */
const CLE_PANIER = 'divix.panier';

function lirePanier() {
    try {
        return JSON.parse(sessionStorage.getItem(CLE_PANIER)) || [];
    } catch (erreur) {
        return [];
    }
}

function ecrirePanier(panier) {
    sessionStorage.setItem(CLE_PANIER, JSON.stringify(panier));
    afficherBarrePanier();
}

const EMOJI_DEFAUT = { Bar: '🍺', Cuisine: '🍽️' };

function grille() {
    return document.getElementById('grille-menu');
}

async function chargerMenu() {
    grille().innerHTML = '<div class="squelette-plat"></div>'.repeat(8);

    try {
        const reponse = await Divix.charger(`${base}/list`);
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

    // Le gérant gère la carte : « Retirer / Remettre ». Les autres commandent.
    let action = '';
    if (modifiable) {
        action = `<span class="ms-auto d-flex gap-1">
                      <button class="btn btn-sm btn-action-voir" onclick="ouvrirModification(${article.id})">Modifier</button>
                      <button class="btn btn-sm ${article.disponible ? 'btn-action-annuler' : 'btn-action-servir'}"
                              onclick="basculerDisponibilite(${article.id}, ${article.disponible ? 0 : 1})">
                          ${article.disponible ? 'Retirer' : 'Remettre'}
                      </button>
                  </span>`;
    } else if (commandable && !indisponible) {
        action = `<button class="btn btn-sm ms-auto btn-action-servir"
                          onclick="ajouterAuPanier(${article.id})">Ajouter</button>`;
    }

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

function ajouterAuPanier(idArticle) {
    const article = articlesMenu.find((element) => element.id === idArticle);
    if (!article) return;

    const panier = lirePanier();
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
    ecrirePanier(panier);
}

function afficherBarrePanier() {
    const barre = document.getElementById('barre-panier');
    if (!barre) return;

    const panier = lirePanier();
    const articles = panier.reduce((somme, ligne) => somme + ligne.quantite, 0);
    const total = panier.reduce((somme, ligne) => somme + ligne.prix * ligne.quantite, 0);

    barre.style.display = articles ? '' : 'none';
    barre.innerHTML = `
        <span class="compte-panier">${articles}</span>
        <span>${Divix.fcfa(total)}</span>
        <span class="fw-semibold">Commander</span>`;
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
        carte.classList.toggle('filtre-masque', !correspond);
        if (correspond) visibles += 1;
    });

    paginationMenu?.rafraichir(true);

    const message = grille().querySelector('.grille-vide');
    if (!visibles && !message) {
        grille().insertAdjacentHTML('beforeend', '<p class="grille-vide">Aucun article ne correspond</p>');
    } else if (visibles && message) {
        message.remove();
    }
}

/* Le formulaire d'article sert à créer comme à modifier : un identifiant
   présent bascule l'envoi vers la route de modification. */
function ouvrirModification(idArticle) {
    const article = articlesMenu.find((element) => element.id === idArticle);
    if (!article) return;

    document.getElementById('articleId').value = article.id;
    document.getElementById('articleNom').value = article.nom;
    document.getElementById('articlePrix').value = article.prix;
    // Le coût de revient est masqué : le champ peut ne pas exister.
    const cout = document.getElementById('articleCout');
    if (cout) cout.value = article.cout_revient || '';
    document.getElementById('articleSeuil').value = article.seuil_alerte || 0;
    document.getElementById('articleGereStock').value = article.gere_stock ? '1' : '0';
    document.getElementById('articleDisponible').value = article.disponible ? '1' : '0';

    const categorie = document.getElementById('articleCategorie');
    [...categorie.options].forEach((option) => {
        option.selected = option.textContent.trim() === article.categorie;
    });

    // La quantité en stock se corrige par un inventaire, pas ici.
    document.getElementById('articleStock').closest('.col').style.display = 'none';
    document.getElementById('blocStock').style.display = article.gere_stock ? '' : 'none';
    document.getElementById('articleModalLabel').textContent = 'Modifier l\'article';
    bootstrap.Modal.getOrCreateInstance(document.getElementById('articleModal')).show();
}

function reinitialiserFormulaireArticle() {
    document.getElementById('articleForm').reset();
    document.getElementById('articleId').value = '';
    document.getElementById('articleStock').closest('.col').style.display = '';
    document.getElementById('blocStock').style.display = 'none';
    document.getElementById('articleModalLabel').textContent = 'Nouvel article';
}

async function basculerDisponibilite(idArticle, disponible) {
    try {
        const reponse = await Divix.envoyer(`${base}/${idArticle}/disponibilite`, { disponible });
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
    base = grille()?.dataset.base || '/menu';
    modifiable = grille()?.dataset.modifiable === '1';
    commandable = grille()?.dataset.commandable === '1';

    paginationMenu = Divix.paginer({
        idConteneur: 'grille-menu',
        idBarre: 'pagination-menu',
        selecteur: '.carte-plat',
        taille: 12,
        libelle: 'articles'
    });

    afficherBarrePanier();
    // Le panier constitué sur la carte n'a d'intérêt qu'une fois validé : la
    // barre ouvre directement le formulaire de commande, sans arrêt sur la
    // liste des tickets.
    document.getElementById('barre-panier')?.addEventListener('click', () => {
        window.location.href = '/commande?nouvelle=1';
    });

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
        url: `${base}/add`,
        idModal: 'articleModal',
        urlDynamique: () => {
            const id = document.getElementById('articleId').value;
            return id ? `${base}/${id}/modifier` : `${base}/add`;
        },
        apres: () => {
            reinitialiserFormulaireArticle();
            chargerMenu();
        }
    });

    // Rouvrir la modale après une modification ne doit pas garder l'ancien article.
    document.getElementById('articleModal')
        ?.addEventListener('hidden.bs.modal', reinitialiserFormulaireArticle);
    document.querySelector('[data-bs-target="#articleModal"]')
        ?.addEventListener('click', reinitialiserFormulaireArticle);

    Divix.brancherFormulaire({
        idBouton: 'submitCategorieBtn',
        idFormulaire: 'categorieForm',
        url: `${base}/categorie/add`,
        idModal: 'categorieModal',
        apres: () => window.location.reload()
    });
});
