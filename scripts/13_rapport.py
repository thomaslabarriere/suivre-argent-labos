"""Étape 8 : compte rendu périodique en PDF, lisible par un journaliste, un élu ou un ministère.
Usage : 13_rapport.py [mois|semaine] [AAAA-MM-JJ fin de période, défaut = dernière date de la base]
Contenu : chiffres clés de la période, évolution sur 12 périodes, qui reçoit, qui paie, nouveaux bénéficiaires,
liens à regarder (sans nom de personne), fiabilité et précautions. Une page de méthode termine le document."""
import sys, datetime as dt, io
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, KeepTogether
from commun import connexion, RACINE

PER = sys.argv[1] if len(sys.argv) > 1 else "mois"
con = connexion()
fin = dt.date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else con.execute("SELECT max(date) FROM lignes WHERE date <= current_date").fetchone()[0]
if PER == "mois":
    # une date en milieu ou début de mois désigne le mois entier (run_mensuel.sh passe AAAA-MM-01)
    deb = fin.replace(day=1); fin = (deb + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1); prev_fin = deb - dt.timedelta(days=1); prev_deb = prev_fin.replace(day=1)
    MOIS = ["janvier","février","mars","avril","mai","juin","juillet","août","septembre","octobre","novembre","décembre"]
    titre_per = f"{MOIS[deb.month-1]} {deb.year}"; unite = "month"
else:
    deb = fin - dt.timedelta(days=fin.weekday()); fin = deb + dt.timedelta(days=6)
    prev_deb, prev_fin = deb - dt.timedelta(days=7), deb - dt.timedelta(days=1)
    titre_per = f"semaine du {deb:%d/%m/%Y} au {fin:%d/%m/%Y}"; unite = "week"
ia = (deb.replace(year=deb.year-1), fin.replace(year=fin.year-1)) if PER == "mois" else (deb - dt.timedelta(weeks=52), fin - dt.timedelta(weeks=52))

# Base de travail : chaque versement avec la structure identifiée (ou non) et son statut de fiabilité.
con.execute("""CREATE OR REPLACE TEMP VIEW v AS
SELECT l.date, l.montant, l.raison_sociale AS labo, l.lien_interet, f.categorie, f.struct_id, f.statut2,
  CASE WHEN f.statut2='fiable' THEN coalesce(f.nom_officiel, f.nom_declare) ELSE f.nom_declare END AS nom,
  f.statut2='fiable' AS identifie,
  CASE WHEN f.statut2='fiable' THEN f.identifiant2 ELSE 's'||f.struct_id END AS ent   -- une entité = un numéro officiel : les variantes d'un même hôpital s'additionnent
FROM lignes l JOIN final2 f USING (struct_id)
WHERE f.categorie NOT IN ('Etudiant','Influenceur','Vétérinaire')""")   # pas de personnes physiques nommées
def per(a, b): return f"date BETWEEN DATE '{a}' AND DATE '{b}'"
P, PP, PA = per(deb, fin), per(prev_deb, prev_fin), per(*ia)
k = con.execute(f"""SELECT sum(montant) FILTER (WHERE {P}), sum(montant) FILTER (WHERE {PP}), sum(montant) FILTER (WHERE {PA}),
  count(*) FILTER (WHERE {P}), count(DISTINCT struct_id) FILTER (WHERE {P}), count(DISTINCT labo) FILTER (WHERE {P}),
  sum(montant) FILTER (WHERE {P} AND identifie) FROM v""").fetchone()
tot, totp, tota, nl, ns, nlab, ident = [x or 0 for x in k]

def eur(x):
    if x >= 1e6: return f"{x/1e6:,.1f} M€".replace(",", " ").replace(".", ",")
    return f"{x:,.0f} €".replace(",", " ")
def var(a, b): return "nouveau" if not b else "faible base" if b < 50000 and a > 3*b else (f"+{100*(a-b)/b:.0f} %" if a >= b else f"{100*(a-b)/b:.0f} %")

# Styles : sobres, lisibles à l'impression.
ENC, GRIS, FOND, ACC = colors.HexColor("#1f2a44"), colors.HexColor("#5b6475"), colors.HexColor("#eef1f6"), colors.HexColor("#0f6b6b")
H1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=ENC, spaceAfter=4)
H2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=ENC, spaceBefore=10, spaceAfter=4)
TX = ParagraphStyle("tx", fontName="Helvetica", fontSize=9.5, leading=13.5, textColor=colors.black)
PT = ParagraphStyle("pt", parent=TX, fontSize=8, leading=10.5, textColor=GRIS)
def tableau(rows, larg, align_num=()):
    t = Table(rows, colWidths=[w*mm for w in larg], repeatRows=1)
    st = [("FONT", (0,0), (-1,0), "Helvetica-Bold", 8.5), ("FONT", (0,1), (-1,-1), "Helvetica", 8.5),
          ("TEXTCOLOR", (0,0), (-1,0), ENC), ("LINEBELOW", (0,0), (-1,0), 0.6, ENC),
          ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, FOND]), ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
          ("TOPPADDING", (0,0), (-1,-1), 2.5), ("BOTTOMPADDING", (0,0), (-1,-1), 2.5)]
    for c in align_num: st.append(("ALIGN", (c,0), (c,-1), "RIGHT"))
    t.setStyle(TableStyle(st)); return t
def court(s, n=48): s = str(s or ""); return s if len(s) <= n else s[:n-1] + "…"
def fig_img(fig, w):
    b = io.BytesIO(); fig.savefig(b, format="png", dpi=200, bbox_inches="tight"); plt.close(fig); b.seek(0)
    im = Image(b); r = im.imageHeight / im.imageWidth; im.drawWidth = w*mm; im.drawHeight = w*mm*r; return im

E = []
E.append(Paragraph("Où va l'argent des laboratoires ?", H1))
E.append(Paragraph(f"Versements de l'industrie de santé aux <b>structures</b> (hôpitaux, associations, sociétés savantes, agences) "
                   f"déclarés dans Transparence Santé, <b>{titre_per}</b>. Compte rendu généré automatiquement le {dt.date.today():%d/%m/%Y}.", TX))
E.append(Spacer(1, 6))
cles = [["Montant versé", "Versements", "Structures payées", "Entreprises qui paient", "Part identifiée*"],
        [eur(tot), f"{nl:,}".replace(",", " "), f"{ns:,}".replace(",", " "), f"{nlab}", f"{100*ident/tot:.0f} %" if tot else "n.d."],
        [f"{var(tot, totp)} vs période précédente", "", "", "", ""], [f"{var(tot, tota)} vs il y a un an", "", "", "", ""]]
t = Table(cles, colWidths=[38*mm]*5)
t.setStyle(TableStyle([("FONT", (0,0), (-1,0), "Helvetica", 8), ("TEXTCOLOR", (0,0), (-1,0), GRIS),
    ("FONT", (0,1), (-1,1), "Helvetica-Bold", 15), ("TEXTCOLOR", (0,1), (-1,1), ENC), ("FONT", (0,2), (-1,-1), "Helvetica", 8),
    ("TEXTCOLOR", (0,2), (-1,-1), ACC), ("BACKGROUND", (0,0), (-1,-1), FOND), ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,1), (-1,1), 6)]))
E.append(t)
E.append(Paragraph("* structure retrouvée avec certitude dans les registres officiels (SIRENE, associations). Le reste est déclaré sans identifiant exploitable.", PT))

# Évolution sur 12 périodes
ev = con.execute(f"""SELECT date_trunc('{unite}', date) p, sum(montant)/1e6 m FROM v
WHERE date BETWEEN DATE '{deb}' - INTERVAL 11 {unite} AND DATE '{fin}' GROUP BY 1 ORDER BY 1""").df()
fig, ax = plt.subplots(figsize=(7.2, 2.2))
ax.bar(ev.p, ev.m, width=20 if PER == "mois" else 5, color=["#0f6b6b" if p.date() >= deb else "#9fb3c8" for p in ev.p])
ax.set_ylabel("M€", fontsize=8); ax.tick_params(labelsize=7); [ax.spines[s].set_visible(False) for s in ("top", "right")]
ax.grid(axis="y", color="#dde3ea", lw=0.6); ax.set_axisbelow(True)
E.append(Paragraph("Évolution sur les 12 dernières périodes", H2)); E.append(fig_img(fig, 175))
E.append(Paragraph("Les entreprises déclarent avec retard : les périodes les plus récentes se complètent encore pendant plusieurs mois.", PT))

# Qui reçoit
top = con.execute(f"""WITH a AS (SELECT ent, min(nom) FILTER (WHERE identifie) nom0, any_value(nom) nom1, any_value(categorie) cat, bool_or(identifie) idf,
  sum(montant) FILTER (WHERE {P}) m, sum(montant) FILTER (WHERE {PP}) mp, count(DISTINCT labo) FILTER (WHERE {P}) nlab FROM v GROUP BY 1)
SELECT ent, coalesce(nom0, nom1), cat, idf, m, mp, nlab FROM a WHERE m > 0 ORDER BY m DESC LIMIT 15""").fetchall()
rows = [["Structure", "Type", "Montant", "Entreprises", "Évolution"]] + [[Paragraph(court(n, 70) + ("" if i else " (?)"), ParagraphStyle("c", parent=TX, fontSize=8, leading=9.5)), court(c, 26), eur(m), str(nl_), var(m, mp or 0)] for _, n, c, i, m, mp, nl_ in top]
E.append(KeepTogether([Paragraph("Les 15 structures qui ont reçu le plus", H2), tableau(rows, [72, 44, 22, 18, 18], (2, 3, 4)),
    Paragraph("(?) : structure non identifiée avec certitude, nom tel que déclaré par l'entreprise.", PT)]))

# Par type de structure
cat = con.execute(f"SELECT categorie, sum(montant)/1e6 m FROM v WHERE {P} GROUP BY 1 ORDER BY 2 DESC LIMIT 8").df()
fig, ax = plt.subplots(figsize=(7.2, 0.32*len(cat)+0.4))
ax.barh([court(c, 45) for c in cat.categorie][::-1], cat.m[::-1], color="#0f6b6b", height=0.6)
for y, val in enumerate(cat.m[::-1]): ax.text(val, y, f" {val:.1f} M€", va="center", fontsize=7)
ax.tick_params(labelsize=7); ax.set_xticks([]); [ax.spines[s].set_visible(False) for s in ("top", "right", "bottom")]
E.append(KeepTogether([Paragraph("Par type de structure", H2), fig_img(fig, 175)]))

# Qui paie
lab = con.execute(f"""SELECT labo, sum(montant) FILTER (WHERE {P}) m, count(DISTINCT struct_id) FILTER (WHERE {P}) n,
  sum(montant) FILTER (WHERE {PP}) mp FROM v GROUP BY 1 HAVING m > 0 ORDER BY m DESC LIMIT 10""").fetchall()
rows = [["Entreprise", "Montant versé", "Structures payées", "Évolution"]] + [[court(l, 55), eur(m), str(n), var(m, mp or 0)] for l, m, n, mp in lab]
E.append(KeepTogether([Paragraph("Les 10 entreprises qui ont le plus versé", H2), tableau(rows, [95, 30, 30, 20], (1, 2, 3))]))

# Nouveaux bénéficiaires
nv = con.execute(f"""WITH a AS (SELECT ent, any_value(nom) nom, any_value(categorie) cat, min(date) d0, sum(montant) FILTER (WHERE {P}) m FROM v GROUP BY 1)
SELECT nom, cat, m FROM a WHERE d0 >= DATE '{deb}' AND m > 0 ORDER BY m DESC LIMIT 8""").fetchall()
if nv:
    rows = [["Structure payée pour la première fois", "Type", "Montant"]] + [[court(n, 60), court(c, 30), eur(m)] for n, c, m in nv]
    E.append(KeepTogether([Paragraph("Nouveaux bénéficiaires", H2), tableau(rows, [100, 50, 25], (2,))]))

# Liens à regarder (agrégés, sans nom de personne)
E.append(Paragraph("Liens à regarder", H2))
cg = con.execute("SELECT count(DISTINCT siren_beneficiaire), count(*) FROM croisement_groupe").fetchone()
cp = con.execute("SELECT count(DISTINCT siren), count(DISTINCT siren) FILTER (WHERE dep_identique) FROM croisement_personnes").fetchone()
E.append(Paragraph(f"• <b>{cg[0]}</b> structure(s) dirigée(s) par des entreprises qui la paient ({cg[1]} liens entreprise-structure). "
    f"Exemple : un groupement de statistiques de ventes administré par les laboratoires qui le financent. Ce n'est pas de l'influence : "
    f"c'est de l'argent que l'industrie se verse à elle-même, à retirer des totaux d'influence.", TX))
E.append(Paragraph(f"• <b>{cp[0]}</b> sociétés dont un dirigeant reçoit aussi personnellement de l'argent de la même entreprise, "
    f"dont <b>{cp[1]}</b> où la personne est payée dans le même département. Les noms ne sont pas publiés ici : "
    f"homonymes possibles, un lien n'est pas une irrégularité. Liste détaillée sur demande, pour vérification.", TX))

# Fiabilité et méthode
E.append(PageBreak()); E.append(Paragraph("Comment ces chiffres sont fabriqués, et jusqu'où on peut s'y fier", H2))
g = con.execute("SELECT round(100*sum(montant) FILTER (WHERE statut2='fiable')/sum(montant),1), round(sum(montant)/1e9,2) FROM final2").fetchone()
tv = con.execute("""SELECT count(*) FILTER (WHERE verdict IN ('juste','faux')), count(*) FILTER (WHERE type_erreur='erreur probable de notre part')
FROM read_csv_auto(?)""", [str(RACINE/"out"/"test_verite.csv")]).fetchone() if (RACINE/"out"/"test_verite.csv").exists() else None
for p in [
  f"<b>Le problème.</b> Dans Transparence Santé, environ 520 000 versements à des structures (soit {str(g[1]).replace('.', ',')} Md€ depuis 2013) "
  "sont déclarés sans identifiant officiel exploitable : on ne sait pas toujours qui a vraiment reçu l'argent, ni additionner ce que reçoit une même structure.",
  f"<b>Ce qui est fait.</b> Chaque nom déclaré est comparé aux registres officiels (SIRENE pour les entreprises et hôpitaux, RNA pour les associations). "
  f"Des règles simples règlent la majorité des cas ; une IA départage les cas difficiles, sans jamais inventer de numéro ; un second modèle relit les plus gros. "
  f"Aujourd'hui, <b>{str(g[0]).replace('.', ',')} % des euros</b> sont rattachés à une structure identifiée avec certitude.",
  ("<b>Taux d'erreur mesuré.</b> Sur " + f"{tv[0]:,}".replace(",", " ") + " structures dont la réponse est connue (l'identifiant était écrit dans la déclaration), "
   f"les règles automatiques se trompent dans <b>{100*tv[1]/tv[0]:.1f} %</b>".replace(".", ",") + f" des cas. Une partie des autres écarts vient d'identifiants mal recopiés par les entreprises elles-mêmes.") if tv else "",
  "<b>Précautions.</b> Un versement déclaré n'est pas une irrégularité : il peut s'agir d'un congrès, d'une étude, d'un contrat de recherche. "
  "Les mois récents sont incomplets. Les montants sont ceux déclarés par les entreprises, sans correction.",
  "<b>Sources.</b> Transparence Santé (base publique des liens d'intérêts), SIRENE (INSEE), Répertoire national des associations, "
  "API recherche-entreprises. Code et méthode ouverts, reproductibles d'une période à l'autre."]:
    if p: E.append(Paragraph(p, TX)); E.append(Spacer(1, 5))

def pied(c, d):
    c.saveState(); c.setFont("Helvetica", 7); c.setFillColor(GRIS)
    c.drawString(18*mm, 10*mm, f"Transparence Santé, structures · {titre_per}"); c.drawRightString(192*mm, 10*mm, f"page {d.page}"); c.restoreState()
out = RACINE/"out"/f"rapport_{PER}_{deb:%Y-%m-%d}.pdf"
SimpleDocTemplate(str(out), pagesize=A4, leftMargin=18*mm, rightMargin=18*mm, topMargin=16*mm, bottomMargin=16*mm,
                  title=f"Où va l'argent des laboratoires ? {titre_per}").build(E, onFirstPage=pied, onLaterPages=pied)
print("PDF :", out)
