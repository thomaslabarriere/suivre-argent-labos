"""Carte des euros reçus par médecin et par département (2025) : SVG pour la page, PNG pour le PDF."""
import json, math, pandas as pd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
from commun import RACINE
D = pd.read_csv(RACINE/"out/departements_euros_par_medecin.csv", dtype={"dep": str}).set_index("dep")
gj = json.load(open(RACINE/"data/ext/geo/departements.geojson"))
SEUILS = [500, 750, 1000, 1250]; COUL = ["#dbe9f6", "#a9cce8", "#6fa8d6", "#3b7fbf", "#1c4f8c"]
def classe(v): return sum(v >= s for s in SEUILS)
W, H = 560, 560; lon0, lat0, k = -5.3, 51.2, 54
def xy(lon, lat): return ((lon - lon0) * k * math.cos(math.radians(46.5)), (lat0 - lat) * k)
paths = []; fig, ax = plt.subplots(figsize=(6.4, 6.4))
for f in gj["features"]:
    code = f["properties"]["code"]; nom = f["properties"]["nom"]
    polys = f["geometry"]["coordinates"] if f["geometry"]["type"] == "MultiPolygon" else [f["geometry"]["coordinates"]]
    kd = "20" if code in ("2A", "2B") else code
    r = D.loc[kd] if kd in D.index else None
    c = COUL[classe(r.eur_par_medecin)] if r is not None and pd.notna(r.eur_par_medecin) else "#e5e7eb"
    d = ""
    for p in polys:
        ring = p[0]; d += "M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in (xy(*pt) for pt in ring)) + "Z"
        ax.add_patch(Polygon([xy(*pt) for pt in ring], closed=True, fc=c, ec="white", lw=0.5 if code != "33" else 1.6, zorder=2 if code != "33" else 3))
        if code == "33": ax.add_patch(Polygon([xy(*pt) for pt in ring], closed=True, fc="none", ec="#111", lw=1.6, zorder=4))
    tip = f"{nom} ({code}) : " + (f"{r.eur_par_medecin:,.0f} € par médecin (rang {r.rang} sur {len(D)}), {r.pct_payes:.0f} % des médecins payés, médiane des payés {r.eur_median_payes:,.0f} €".replace(",", " ") if r is not None else "pas de données")
    paths.append(f'<path d="{d}" fill="{c}" class="dep{" gir" if code == "33" else ""}" data-t="{tip}"><title>{tip}</title></path>')
ax.set_xlim(0, W); ax.set_ylim(H, 0); ax.set_aspect("equal"); ax.axis("off")
from matplotlib.patches import Patch
lab = ["moins de 500 €", "500 à 750 €", "750 à 1 000 €", "1 000 à 1 250 €", "1 250 € et plus"]
ax.legend([Patch(fc=c) for c in COUL], lab, loc="lower left", fontsize=8, frameon=False, title="€ reçus par médecin, 2025", title_fontsize=8)
# DOM : absents du fond de carte (métropole seule) ; leurs valeurs sont données en encart texte, même échelle de couleurs.
NOMS_DOM = {"971": "Guadeloupe", "972": "Martinique", "973": "Guyane", "974": "La Réunion", "976": "Mayotte"}
dom = [(c, n, D.loc[c]) for c, n in NOMS_DOM.items() if c in D.index]
ax.text(W - 4, H - 8, "Outre-mer (hors carte)\n" + "\n".join(f"{n} : {r.eur_par_medecin:,.0f} €".replace(",", " ") for c, n, r in dom),
        ha="right", va="bottom", fontsize=7.5, linespacing=1.5, bbox=dict(fc="white", ec="#9ca3af", lw=0.6, boxstyle="round,pad=0.4"))
plt.tight_layout(); plt.savefig(RACINE/"out/carte_euros_par_medecin.png", dpi=170); plt.close()
leg = "".join(f'<span class="lg"><i style="background:{c}"></i>{l}</span>' for c, l in zip(COUL, lab))
leg += '<span class="lg">Outre-mer, hors carte : ' + " ; ".join(f'<i style="background:{COUL[classe(r.eur_par_medecin)]}"></i>{n} {r.eur_par_medecin:,.0f} €'.replace(",", " ") for c, n, r in dom) + "</span>"
svg = f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Carte des euros reçus par médecin et par département en 2025" class="carte">{"".join(paths)}</svg><div class="legende">{leg}</div>'
open(RACINE/"out/carte.svg.html", "w").write(svg); print("ok", len(svg)//1024, "Ko")
