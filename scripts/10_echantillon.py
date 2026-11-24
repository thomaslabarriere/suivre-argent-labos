"""Étape 6 : échantillon de contrôle des rattachements « fiables », à vérifier à la main.
60 tirés au hasard (erreur en nombre de structures) + 40 tirés au prorata des euros (erreur en euros).
Chaque ligne a un lien vers la fiche officielle pour vérifier en 10 secondes."""
import pandas as pd
from commun import connexion, RACINE
con = connexion()
df = con.execute("""SELECT f.struct_id, f.nom_declare, s.variantes, f.categorie, f.dep, s.adresses[1] adresse, round(f.montant) montant,
  f.identifiant2 identifiant, f.methode2 methode, coalesce(u.denomination, r.titre) nom_officiel, u.sigle,
  CAST(u.cat_juridique AS VARCHAR) cat_juridique
FROM final2 f JOIN structures s USING (struct_id)
LEFT JOIN ref_ul u ON u.siren=f.identifiant2 LEFT JOIN ref_rna r ON r.rna=f.identifiant2
WHERE f.statut2='fiable'""").df()
df = df.sort_values("struct_id").reset_index(drop=True)   # ordre fixe : le tirage (graine fixe) est reproductible
a = df.sample(60, random_state=1)
r = df.drop(a.index); b = r.sample(40, weights=r.montant.clip(upper=5e6), random_state=2)  # plafond 5 M€ pour que le tirage reste possible
e = pd.concat([a.assign(tirage="hasard"), b.assign(tirage="au prorata des euros")])
e["fiche"] = ["https://www.data-asso.fr/annuaire/association/"+i if str(i).startswith("W") else "https://annuaire-entreprises.data.gouv.fr/entreprise/"+str(i) for i in e.identifiant]
e["variantes"] = [" | ".join(list(v)[:3]) for v in e.variantes]
e["correct (oui/non/doute)"] = ""; e["commentaire"] = ""
out = RACINE/"out"/"controle_100.csv"
e.drop(columns=["struct_id"]).to_csv(out, index=False)
e[["struct_id","nom_declare","variantes","categorie","dep","adresse","identifiant","nom_officiel","sigle","cat_juridique","methode"]].to_json(
    RACINE/"data"/"arbitrage"/"controle_100.jsonl", orient="records", lines=True, force_ascii=False)
print(out, len(e), "lignes ;", e.methode.value_counts().to_dict())
