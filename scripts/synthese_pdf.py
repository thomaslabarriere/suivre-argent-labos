"""Synthèse de deux pages à faire circuler (docs/synthese.pdf). Aucun nom de personne.
Les chiffres viennent de docs/chiffres_cles.json : la synthèse ne peut pas contredire les autres documents."""
import json, pathlib
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether)
from reportlab.graphics.shapes import Drawing, Rect, String

RAC = pathlib.Path(__file__).resolve().parent.parent
C = {k: v for k, v in json.loads((RAC / "docs/chiffres_cles.json").read_text()).items()}
t = lambda k: C[k]["texte"]
v = lambda k: C[k]["valeur"]
DEPOT = "github.com/thomaslabarriere/suivre-argent-labos"

ENCRE, BLEU, GRIS, FOND, ROUGE = (colors.HexColor(x) for x in ("#1b2a3a", "#1f5f8b", "#6b7785", "#eef3f7", "#b4442c"))
S = lambda nom, **k: ParagraphStyle(nom, fontName=k.pop("f", "Helvetica"), textColor=k.pop("c", ENCRE), **k)
TITRE = S("t", f="Helvetica-Bold", fontSize=19, leading=23)
SOUS = S("s", fontSize=9.5, leading=13, c=GRIS)
H = S("h", f="Helvetica-Bold", fontSize=11.5, leading=15, c=BLEU, spaceBefore=9, spaceAfter=4)
B = S("b", fontSize=9.2, leading=12.6)
PETIT = S("p", fontSize=7.8, leading=10.4, c=GRIS)
CHIFFRE = S("c", f="Helvetica-Bold", fontSize=15, leading=17, c=BLEU)
LEG = S("l", fontSize=8.4, leading=11)


def puces(items):
    return [Paragraph("•&nbsp;&nbsp;" + x, ParagraphStyle("pu", parent=B, leftIndent=9, firstLineIndent=-9, spaceAfter=2.5)) for x in items]


def tuiles(rows):
    data = [[Paragraph(c, CHIFFRE), Paragraph(l, LEG)] for c, l in rows]
    tb = Table(data, colWidths=[38 * mm, 132 * mm])
    tb.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor("#d5dde5")),
                            ("TOPPADDING", (0, 0), (-1, -1), 4.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5)]))
    return tb


def barre():
    """Où va l'argent déclaré : double compte, prestataires, acteurs de santé (même échelle)."""
    brut = v("total brut déclaré"); w = 170 * mm; d = Drawing(w, 30 * mm)
    parts = [(v("hors prestataires"), BLEU, "acteurs de santé " + t("hors prestataires")),
             (v("prestataires"), colors.HexColor("#7fa7c4"), "prestataires " + t("prestataires")),
             (v("double compte"), colors.HexColor("#c9d1d9"), "compté deux fois " + t("double compte"))]
    x = 0
    for val, coul, lib in parts:
        l = w * val / brut
        d.add(Rect(x, 12 * mm, l - 1.5, 8 * mm, fillColor=coul, strokeColor=None))
        d.add(String(x + 2, 6.5 * mm, lib, fontName="Helvetica", fontSize=7.6, fillColor=ENCRE))
        x += l
    d.add(String(0, 23 * mm, f"Les {t('total brut déclaré')} déclarés de 2012 à 2026 :", fontName="Helvetica-Bold", fontSize=8.6, fillColor=ENCRE))
    return d


st = [Paragraph("Suivre l'argent des laboratoires", TITRE),
      Paragraph(f"Ce que permettent Transparence Santé et dix autres bases publiques. Travail issu du hackathon Data For Good "
                f"Bordeaux du 24 novembre 2026. Code, données et méthode : <b>{DEPOT}</b>", SOUS), Spacer(1, 6),
      Paragraph("Ce qui a été construit", H)]
st += puces([
    f"<b>Le rattachement des structures sans identifiant.</b> 520 000 versements vers des hôpitaux, associations et "
    f"sociétés savantes n'ont ni SIREN ni RNA. {t('structures rattachées de façon fiable')} structures sont désormais "
    f"rattachées à leur identifiant officiel (78 % des euros), avec une erreur mesurée de {t('erreur probable du rattachement')}.",
    "<b>Les croisements</b> avec les remboursements de l'Assurance maladie, les avis de la HAS, la HATVP (lobbying, "
    "déclarations d'intérêts), l'annuaire des soignants, les marchés publics et les essais cliniques.",
    "<b>Une chaîne vérifiée :</b> 74 tests automatiques, un contrat qui détecte un changement de format des sources, "
    "181 contrôles avant chaque publication. Tout se relance d'une commande, résultats reproductibles."])
st += [Paragraph("Ce que montrent les données", H), barre(), Spacer(1, 2)]
st += [tuiles([
    (t("double compte"), "sont comptés deux fois par quiconque additionne simplement la base : une convention et les "
     "rémunérations qui l'exécutent sont déclarées séparément, avec le même argent."),
    (t("prestataires"), f"vont à des prestataires (agences de communication, recherche sous contrat, informatique, "
     f"conseil, grossistes), soit {100 * v('prestataires') / v('total net'):.0f} % du net. Il reste {t('hors prestataires')} pour les acteurs de santé."),
    (t("plus grosse ligne"), f"en une seule déclaration, soit {t('part de la plus grosse ligne')} du total net : très "
     f"probablement une virgule déplacée. {t('lignes de 10 M€ ou plus')} de 10 M€ ou plus font {t('part des lignes de 10 M€ ou plus')} du total."),
    (t("part des rémunérations sans motif"), f"des rémunérations versées aux soignants ({t('rémunérations sans motif')} sur "
     f"{t('rémunérations aux professionnels')}) n'ont ni motif, ni texte libre, ni événement."),
    (t("remboursé ASMR V"), f"remboursés en 2025 ({t('part ASMR V')}) pour des médicaments sans amélioration du service "
     f"médical rendu selon la HAS (ASMR V)."),
    (t("part du 1 % le mieux payé"), f"de l'argent versé aux soignants va à 1 % d'entre eux. Médiane : {t('médiane par professionnel')} ; "
     f"{t('professionnels au-dessus de 100 000 €')} personnes dépassent 100 000 €."),
    (t("euros par spécialiste"), f"par an en moyenne pour un spécialiste, contre {t('euros par généraliste')} pour un "
     f"généraliste, alors que les généralistes prescrivent deux fois plus en ville."),
])]
st += [PageBreak(), Paragraph("Ce qui est réutilisable tout de suite", H)]
st += puces([
    "<b>La table de rattachement</b> (<i>resultats/rattachement_structures.csv</i>) : pour chacune des 88 105 structures "
    "sans identifiant, son SIREN ou RNA, la méthode et la confiance. Elle se joint à tout extrait de la base.",
    "<b>Deux règles à reprendre partout :</b> la vue sans double compte, et l'identité d'un soignant (les identifiants "
    "factices comme « [SO] » ou « 0 » réunissent sinon des milliers de personnes sous un seul nom).",
    "<b>Le marquage des prestataires</b> ligne à ligne, et <b>la liste des déclarations invraisemblables</b> à faire "
    "vérifier par les déclarants.",
    f"<b>Des croisements prêts</b> : élus portant le nom d'un soignant payé ({t('élus bénéficiaires')}, comparés à leurs "
    f"déclarations HATVP), experts des commissions de la HAS ({t('experts HAS retrouvés')} retrouvés), hôpitaux payés "
    f"par un labo et qui lui passent des marchés ({t('paires hôpital × labo')}), lobbying des groupes payeurs.",
    "<b>L'arbitrage par IA</b> : consignes, lots et décisions publiés ; l'IA ne choisit qu'entre des candidats trouvés "
    "dans les registres et n'invente jamais de numéro. Rejouable sans IA."])
st += [Paragraph("Ce que changerait le plus la base elle-même", H)]
st += puces([
    "Exiger et contrôler un identifiant (SIREN, RNA, FINESS, RPPS valide) à la saisie : le rattachement deviendrait inutile.",
    "Publier une vue nette, ou un indicateur « convention exécutée par des versements déclarés ».",
    "Contrôler la vraisemblance des montants (un hébergement à 1,3 M€, une convention à 445 M€) et rendre le motif "
    "obligatoire pour les rémunérations.",
    "Publier le groupe de chaque entreprise déclarante et le produit concerné (CIS, code LPP)."])
st += [Paragraph("Ce qu'on pourrait faire ensuite", H)]
st += puces([
    "Un site de consultation « qui est qui » : marque, labo, établissement, département, avec la vue nette et les précautions.",
    "Mesurer si les versements précèdent les hausses de prescription d'un produit, par spécialité et département.",
    "Confronter les versements aux déclarations d'intérêts non publiées en open data (HATVP, DPI-Santé)."])
st += [Spacer(1, 8), KeepTogether([Paragraph(
    "<b>Précautions.</b> Un lien d'intérêt n'est pas une irrégularité : ces versements sont légaux et déclarés. Un montant "
    "inhabituel peut être une erreur du déclarant. Les rapprochements par nom comportent des homonymes possibles : "
    "chaque cas se vérifie avant d'être cité. Les fichiers nominatifs, avec leurs précautions, sont dans le dépôt.", PETIT),
    Spacer(1, 5), Paragraph(f"Thomas Labarriere · t.labarriere12@gmail.com · {DEPOT}", PETIT)])]


def fond(c, doc):
    c.saveState(); c.setFillColor(BLEU); c.rect(0, A4[1] - 5 * mm, A4[0], 5 * mm, stroke=0, fill=1)
    c.setFont("Helvetica", 7.5); c.setFillColor(GRIS); c.drawRightString(A4[0] - 20 * mm, 10 * mm, f"{doc.page} / 2"); c.restoreState()


doc = SimpleDocTemplate(str(RAC / "docs/synthese.pdf"), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=17 * mm,
                        bottomMargin=16 * mm, title="Suivre l'argent des laboratoires : synthèse", author="Thomas Labarriere")
doc.build(st, onFirstPage=fond, onLaterPages=fond)
print("docs/synthese.pdf")
