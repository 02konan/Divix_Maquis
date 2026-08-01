/* Activation des fonctionnalités du maquis. */

async function basculerModule(interrupteur) {
    const cle = interrupteur.dataset.cle;
    const actif = interrupteur.checked;
    interrupteur.disabled = true;

    try {
        const reponse = await Divix.envoyer('/administration/modules', {
            cle: cle,
            actif: actif ? '1' : '0'
        });

        if (!reponse.success) {
            interrupteur.checked = !actif;
            Divix.erreur(reponse.error || "Modification impossible");
            return;
        }

        // Le menu latéral reflète les fonctionnalités actives : on le recharge.
        await Divix.succes(reponse.message);
        window.location.reload();
    } catch (erreur) {
        console.error(erreur);
        interrupteur.checked = !actif;
        Divix.erreur("Modification impossible");
    } finally {
        interrupteur.disabled = false;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.bascule-module').forEach((interrupteur) => {
        interrupteur.addEventListener('change', () => basculerModule(interrupteur));
    });
});
