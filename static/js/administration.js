/* Administration : les comptes du personnel.
 *
 * Les fonctionnalités du maquis ne se règlent plus ici mais depuis la console
 * de l'éditeur : ce que l'on souscrit ne se donne pas soi-même. */

/* ------------------------------------------------------------------ */
/* Comptes du personnel                                               */
/* ------------------------------------------------------------------ */

async function envoyerEtRecharger(url, donnees, elementARetablir = null, valeurInitiale = null) {
    try {
        const reponse = await Divix.envoyer(url, donnees);
        if (!reponse.success) {
            if (elementARetablir) elementARetablir.checked = valeurInitiale;
            Divix.erreur(reponse.error || "Modification impossible");
            return;
        }
        await Divix.succes(reponse.message);
        window.location.reload();
    } catch (erreur) {
        console.error(erreur);
        if (elementARetablir) elementARetablir.checked = valeurInitiale;
        Divix.erreur("Modification impossible");
    }
}

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.bascule-utilisateur').forEach((interrupteur) => {
        interrupteur.addEventListener('change', () => {
            envoyerEtRecharger(
                `/administration/utilisateurs/${interrupteur.dataset.id}/actif`,
                { actif: interrupteur.checked ? '1' : '0' },
                interrupteur,
                !interrupteur.checked
            );
        });
    });

    document.querySelectorAll('.role-utilisateur').forEach((selecteur) => {
        selecteur.addEventListener('change', () => {
            envoyerEtRecharger(
                `/administration/utilisateurs/${selecteur.dataset.id}/role`,
                { id_role: selecteur.value }
            );
        });
    });

    document.querySelectorAll('.mot-de-passe-utilisateur').forEach((bouton) => {
        bouton.addEventListener('click', async () => {
            const { value: motDePasse } = await Swal.fire({
                title: `Mot de passe de ${bouton.dataset.nom}`,
                input: 'text',
                inputPlaceholder: '6 caractères minimum',
                showCancelButton: true,
                cancelButtonText: 'Annuler',
                confirmButtonText: 'Réinitialiser',
                confirmButtonColor: '#3d6dff'
            });
            if (!motDePasse) return;
            envoyerEtRecharger(
                `/administration/utilisateurs/${bouton.dataset.id}/motdepasse`,
                { mot_de_passe: motDePasse }
            );
        });
    });

    Divix.brancherFormulaire({
        idBouton: 'submitUtilisateurBtn',
        idFormulaire: 'utilisateurForm',
        url: '/administration/utilisateurs',
        idModal: 'utilisateurModal',
        apres: () => window.location.reload()
    });
});
