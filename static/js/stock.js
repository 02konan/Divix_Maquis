/* Suivi des stocks de boissons et journal des mouvements. */

let appliquerFiltresStock = null;
let paginationStock = null;
let paginationMouvements = null;

async function chargerStock() {
    Divix.chargement('tbody-stock', 6);
    Divix.chargement('tbody-mouvements', 5);

    try {
        const reponse = await Divix.charger('/stock/list');
        Divix.compteurs(reponse.counter);
        afficherStock(reponse.data || []);
        afficherMouvements(reponse.mouvements || []);
        paginationStock?.rafraichir(true);
        paginationMouvements?.rafraichir(true);
    } catch (erreur) {
        console.error(erreur);
        Divix.vide('tbody-stock', 'Impossible de charger les stocks', 6);
        Divix.vide('tbody-mouvements', 'Aucun mouvement', 5);
    }
}

function afficherStock(articles) {
    if (!articles.length) {
        Divix.vide('tbody-stock', 'Aucun article suivi en stock', 6);
        return;
    }

    document.getElementById('tbody-stock').innerHTML = articles.map((article) => `
        <tr data-statut="${Divix.echapper(article.statut)}">
            <td data-label="Article">
                <p class="m-0 p-0">${Divix.echapper(article.nom)}</p>
                <span class="text-muted small">${Divix.echapper(article.reference)}</span>
            </td>
            <td data-label="Catégorie">${Divix.echapper(article.categorie)}</td>
            <td data-label="Stock"><span class="fw-medium">${article.stock}</span></td>
            <td data-label="Seuil"><span class="text-muted">${article.seuil_alerte}</span></td>
            <td data-label="Valeur">${Divix.fcfa(article.valeur_stock)}</td>
            <td data-label="Statut">${Divix.badge(article.statut)}</td>
        </tr>`).join('');

    appliquerFiltresStock?.();
}

function afficherMouvements(mouvements) {
    if (!mouvements.length) {
        Divix.vide('tbody-mouvements', 'Aucun mouvement enregistré', 5);
        return;
    }

    document.getElementById('tbody-mouvements').innerHTML = mouvements.map((mouvement) => `
        <tr>
            <td data-label="Article"><span class="small">${Divix.echapper(mouvement.article)}</span></td>
            <td data-label="Type">${Divix.badge(mouvement.type_mouvement)}</td>
            <td data-label="Qté">${mouvement.quantite}</td>
            <td data-label="Reste">${mouvement.stock_apres}</td>
            <td data-label="Date"><span class="text-muted small">${Divix.date(mouvement.date_mouvement, true)}</span></td>
        </tr>`).join('');
}

document.addEventListener('DOMContentLoaded', () => {
    chargerStock();

    paginationStock = Divix.paginer({
        idConteneur: 'tbody-stock',
        idBarre: 'pagination-stock',
        taille: 10,
        libelle: 'articles'
    });
    paginationMouvements = Divix.paginer({
        idConteneur: 'tbody-mouvements',
        idBarre: 'pagination-mouvements',
        taille: 10,
        libelle: 'mouvements'
    });

    appliquerFiltresStock = Divix.brancherFiltres({
        idTbody: 'tbody-stock',
        idRecherche: 'searchInput',
        apres: () => {
            paginationStock.rafraichir(true);
            paginationMouvements.rafraichir(true);
        }
    });

    // Un inventaire saisit le stock réel constaté, pas un écart.
    const selecteurType = document.getElementById('mouvementType');
    const champQuantite = document.getElementById('mouvementQuantite');
    selecteurType?.addEventListener('change', () => {
        const estInventaire = selecteurType.value === 'Inventaire';
        champQuantite.previousElementSibling.innerHTML = estInventaire
            ? 'Stock réel compté <span class="small text-danger">*</span>'
            : 'Quantité <span class="small text-danger">*</span>';
        champQuantite.min = estInventaire ? 0 : 1;
    });

    Divix.brancherFormulaire({
        idBouton: 'submitMouvementBtn',
        idFormulaire: 'mouvementForm',
        url: '/stock/mouvement',
        idModal: 'mouvementModal',
        apres: () => window.location.reload()
    });
});
