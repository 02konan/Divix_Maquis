/* Dashboard : indicateurs du service, courbe de recette et dernières commandes. */

const IDS_COMPTEURS = [
    'ca-jour', 'commandes-jour', 'ticket-moyen', 'tables-occupees',
    'ca-percentage', 'commandes-percentage'
];

let graphiqueRecette = null;

async function rafraichirDashboard() {
    Divix.chargement('dernieres-commandes-body', 6);
    Divix.squelette(IDS_COMPTEURS, true);

    try {
        const reponse = await Divix.charger('/dashboard/data');
        if (!reponse.success) throw new Error(reponse.error);

        Divix.squelette(IDS_COMPTEURS, false);
        const donnees = reponse.data;

        afficherIndicateurs(donnees);
        afficherGraphique(donnees.ca_par_jour || []);
        afficherTopArticles(donnees.top_articles || []);
        afficherDernieresCommandes(donnees.dernieres_commandes || []);
    } catch (erreur) {
        console.error('Erreur dashboard:', erreur);
        Divix.squelette(IDS_COMPTEURS, false);
        afficherErreur("Erreur lors du chargement des données");
    }
}

function afficherIndicateurs(donnees) {
    Divix.animerNombre(document.getElementById('ca-jour'), donnees.ca_jour);
    Divix.animerNombre(document.getElementById('commandes-jour'), donnees.commandes_jour);
    Divix.animerNombre(document.getElementById('ticket-moyen'), donnees.ticket_moyen);
    Divix.animerNombre(document.getElementById('tables-occupees'), donnees.tables_occupees);

    document.getElementById('total-tables').textContent = ` / ${donnees.total_tables} tables`;
    document.getElementById('couverts-jour').textContent = `${donnees.couverts_jour} couverts`;

    const impaye = document.getElementById('impaye-jour');
    impaye.textContent = `${Divix.fcfa(donnees.montant_impaye)} en attente`;
    impaye.className = `ms-auto badge ${donnees.montant_impaye > 0 ? 'badge-pending' : 'badge-success'}`;

    afficherPourcentage('ca-percentage', donnees.pourcentages?.ca);
    afficherPourcentage('commandes-percentage', donnees.pourcentages?.commandes);
}

function afficherPourcentage(id, valeur) {
    const element = document.getElementById(id);
    if (!element) return;
    const pourcentage = valeur ?? 0;
    element.textContent = `${pourcentage >= 0 ? '+' : ''}${pourcentage}% ce mois`;
    element.className = `ms-auto badge ${pourcentage >= 0 ? 'badge-success' : 'badge-danger'}`;
}

function afficherGraphique(serie) {
    const conteneur = document.getElementById('ventes-chart');
    if (!conteneur) return;

    if (!serie.length) {
        conteneur.innerHTML = '<p class="text-center text-muted small m-0">Aucune donnée à afficher</p>';
        return;
    }

    conteneur.innerHTML = '<canvas id="barChart"></canvas>';
    const contexte = document.getElementById('barChart').getContext('2d');

    if (graphiqueRecette) graphiqueRecette.destroy();

    graphiqueRecette = new Chart(contexte, {
        type: 'bar',
        data: {
            labels: serie.map((jour) => jour.date),
            datasets: [
                {
                    label: 'Commandes',
                    data: serie.map((jour) => jour.nombre_commandes),
                    backgroundColor: '#1C1C1C',
                    borderRadius: 6,
                    borderSkipped: false
                },
                {
                    type: 'line',
                    label: 'Recette',
                    data: serie.map((jour) => jour.revenu),
                    borderColor: '#3d6dff',
                    backgroundColor: 'rgba(61,109,255,0.16)',
                    borderWidth: 2,
                    tension: 0.35,
                    fill: true,
                    yAxisID: 'y1',
                    pointRadius: 3,
                    pointBackgroundColor: '#3d6dff'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: true, labels: { color: '#444' } },
                tooltip: {
                    backgroundColor: 'rgba(0,0,0,.75)',
                    padding: 10,
                    cornerRadius: 6,
                    callbacks: {
                        label: (contexteTooltip) => contexteTooltip.dataset.type === 'line'
                            ? `Recette : ${Divix.fcfa(contexteTooltip.parsed.y)}`
                            : `${contexteTooltip.parsed.y} commandes`
                    }
                }
            },
            scales: {
                x: { grid: { display: false }, ticks: { font: { size: 11 }, color: '#888' } },
                y: {
                    position: 'left',
                    beginAtZero: true,
                    grid: { color: 'rgba(0,0,0,.05)' },
                    ticks: { color: '#888', font: { size: 11 }, precision: 0 }
                },
                y1: {
                    position: 'right',
                    beginAtZero: true,
                    grid: { display: false },
                    ticks: {
                        color: '#3d6dff',
                        font: { size: 11 },
                        callback: (valeur) => Divix.montant(valeur)
                    }
                }
            }
        }
    });
}

function afficherTopArticles(articles) {
    const conteneur = document.getElementById('top-articles');
    if (!conteneur) return;

    if (!articles.length) {
        conteneur.innerHTML = '<p class="small text-muted m-0">Aucune vente enregistrée</p>';
        return;
    }

    const maximum = Math.max(...articles.map((article) => article.quantite));

    conteneur.innerHTML = articles.map((article, index) => `
        <div class="top-article">
            <div class="d-flex align-items-center gap-2">
                <span class="rang">${index + 1}</span>
                <span class="fw-medium">${Divix.echapper(article.nom)}</span>
                <span class="ms-auto small text-muted">${article.quantite} vendus</span>
            </div>
            <div class="barre-top mt-1">
                <span style="width:${Math.round((article.quantite / maximum) * 100)}%"></span>
            </div>
            <span class="small text-muted">${Divix.fcfa(article.revenu)}</span>
        </div>
    `).join('');
}

function afficherDernieresCommandes(commandes) {
    const corps = document.getElementById('dernieres-commandes-body');
    if (!corps) return;

    if (!commandes.length) {
        Divix.vide('dernieres-commandes-body', 'Aucune commande enregistrée', 6);
        return;
    }

    corps.innerHTML = commandes.map((commande) => `
        <tr>
            <td data-label="Référence" class="no-start"><span class="text-muted small">${Divix.echapper(commande.reference)}</span></td>
            <td data-label="Client">${Divix.echapper(commande.client)}</td>
            <td data-label="Table">${Divix.echapper(commande.table)}</td>
            <td data-label="Statut">${Divix.badge(commande.statut)}</td>
            <td data-label="Montant">${Divix.fcfa(commande.montant)}</td>
            <td data-label="Date">${Divix.date(commande.date, true)}</td>
        </tr>
    `).join('');
}

function afficherErreur(message) {
    const element = document.getElementById('dashboard-error');
    if (!element) return;
    element.textContent = message;
    element.style.display = 'block';
    setTimeout(() => { element.style.display = 'none'; }, 5000);
}

document.addEventListener('DOMContentLoaded', () => {
    rafraichirDashboard();
    setInterval(rafraichirDashboard, 5 * 60 * 1000);
});
