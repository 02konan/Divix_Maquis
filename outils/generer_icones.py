"""Régénère static/vendor/boxicons/boxicons.css à partir des classes utilisées.

Seules les icônes réellement posées dans les gabarits, le JS et backend/roles.py
sont embarquées : les trois polices Boxicons complètes pèsent plusieurs centaines
de kilo-octets pour une douzaine de glyphes.

    python outils/generer_icones.py

Les tracés viennent du paquet npm @iconify-json/boxicons, qui publie le jeu
Boxicons 3. Le script a donc besoin d'un accès au registre npm.
"""

import io
import json
import re
import tarfile
import urllib.parse
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
CIBLE = RACINE / "static/vendor/boxicons/boxicons.css"
PAQUET = "https://registry.npmjs.org/@iconify-json%2fboxicons"
MOTIF_CLASSE = re.compile(r"\b(bxf|bx|bxb) (bx-[a-z0-9-]+)")

ENTETE = """/* Icônes Boxicons 3, servies localement — fichier généré.
 *
 * Seules les icônes réellement utilisées sont embarquées. Chaque icône est un
 * masque SVG teinté par `currentColor` : elle hérite donc de la couleur et de
 * la taille du texte, comme le ferait une police.
 *
 * Pour en ajouter une : poser la classe dans le gabarit, puis relancer
 * `python outils/generer_icones.py`.
 */

.bx,
.bxf,
.bxb {
    display: inline-block;
    width: 1em;
    height: 1em;
    vertical-align: -0.125em;
    background-color: currentColor;
    -webkit-mask: var(--bx-icone) no-repeat center / contain;
    mask: var(--bx-icone) no-repeat center / contain;
}

"""


def telecharger_jeu():
    with urllib.request.urlopen(PAQUET, timeout=60) as reponse:
        infos = json.load(reponse)
    version = infos["dist-tags"]["latest"]
    with urllib.request.urlopen(
        infos["versions"][version]["dist"]["tarball"], timeout=120
    ) as reponse:
        archive = tarfile.open(fileobj=io.BytesIO(reponse.read()))
    with archive.extractfile("package/icons.json") as fichier:
        return json.load(fichier)


def classes_utilisees():
    sources = list((RACINE / "templates").rglob("*.html"))
    sources += list((RACINE / "static/js").glob("*.js"))
    sources += [RACINE / "backend/roles.py"]

    utilisees = set()
    for fichier in sources:
        utilisees.update(MOTIF_CLASSE.findall(fichier.read_text(encoding="utf-8")))
    return sorted(utilisees)


def main():
    jeu = telecharger_jeu()
    largeur, hauteur = jeu.get("width", 24), jeu.get("height", 24)

    regles, manquantes = [], []
    for prefixe, classe in classes_utilisees():
        nom = classe[3:]
        # La variante pleine porte le suffixe -filled dans le jeu Boxicons 3.
        cle = f"{nom}-filled" if prefixe == "bxf" else nom
        icone = jeu["icons"].get(cle)
        if not icone:
            manquantes.append(f"{prefixe} {classe} (cherché : {cle})")
            continue
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {largeur} {hauteur}">'
            f'{icone["body"]}</svg>'
        )
        # Guillemets simples dans le SVG : des doubles refermeraient la chaîne
        # CSS `url("...")` et la règle serait ignorée en silence.
        donnee = urllib.parse.quote(svg.replace('"', "'"), safe="/:=<>' ")
        regles.append(
            f'.{prefixe}.{classe} {{ --bx-icone: url("data:image/svg+xml,{donnee}"); }}'
        )

    if manquantes:
        raise SystemExit(
            "Ces classes n'existent pas dans Boxicons 3 :\n  " + "\n  ".join(manquantes)
        )

    CIBLE.write_text(ENTETE + "\n".join(regles) + "\n", encoding="utf-8")
    print(f"{len(regles)} icônes écrites dans {CIBLE.relative_to(RACINE)}")


if __name__ == "__main__":
    main()
