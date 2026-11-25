"""Piste 1 (24/11) : les experts de la HAS qui évaluent les médicaments (Commission de la Transparence, CT)
et les dispositifs (CNEDiMTS) reçoivent-ils de l'argent des laboratoires ?

1. Membres : listes publiques has-sante.fr (pages de composition + décisions de nomination du collège), écrites ici
   en dur avec leur URL source -> data/ext/has/membres_commissions.csv. Aucun accès à DPI-Santé (captcha).
2. Recherche dans Transparence Santé (professionnels 'PRS') par nom + prénom normalisés (sans accents, ponctuation).
3. Levée des homonymes : on regroupe les lignes par personne (RPPS ; sans RPPS : département) et on compare au
   département indiqué sur la page HAS et à la profession.
   - sûre     : même RPPS sur >= 2 lignes + département HAS retrouvé + profession compatible
   - probable : département retrouvé (RPPS sur 1 ligne, ou sans RPPS), ou département HAS inconnu mais RPPS unique multi-lignes
   - homonyme possible : département ou profession ne concordent pas / plusieurs personnes possibles
Sorties : out/experts_has_versements.csv (1 ligne/membre), out/experts_has_detail_labos.csv (membre x labo).
Un lien d'intérêt n'est pas une irrégularité : les membres déclarent leurs liens, la HAS gère les déports.
Montants nets : une convention exécutée par des rémunérations ou avantages liés (convention_liee) n'est comptée qu'une fois."""
import os, re, pandas as pd, duckdb
from commun import RACINE, vues_ts
OUT = RACINE / "out"; HAS = RACINE / "data/ext/has"; HAS.mkdir(parents=True, exist_ok=True)

U_CT = "https://www.has-sante.fr/jcms/c_412210/fr/commission-de-la-transparence-ct"
U_CT24 = "https://www.has-sante.fr/jcms/p_3555770/fr/decision-n-2024-0265/dc/sem-du-10-octobre-2024-du-college-de-la-haute-autorite-de-sante-portant-nomination-des-membres-de-la-commission-de-la-transparence (décision 2024.0265/DC/SEM)"
U_CT25 = "https://www.has-sante.fr/jcms/p_3633603/fr/decision-n-2025-0157 (décision 2025.0157/DC/SEM du 26/06/2025)"
U_CT26a = "https://www.has-sante.fr/jcms/p_4027825/fr/decision-n-2026-0051 (décision 2026.0051/DC/SEM du 12/03/2026)"
U_CT26b = "https://www.has-sante.fr/jcms/p_4081294/fr/decision-n-2026-0098 (décision 2026.0098/DC/SEM du 11/06/2026)"
U_CT26c = "https://www.has-sante.fr/jcms/p_4027841/fr/decision-n-2026-0084 (décision 2026.0084/DC/SEM du 13/05/2026)"
U_CN = "https://www.has-sante.fr/jcms/c_419486/fr/cnedimts"
D0, D1 = "2024-11-11", "2027-11-10"   # mandat CT
C0, C1 = "2024-11-06", "2027-11-05"   # mandat CNEDiMTS

# (prénom, nom, rôle, spécialité page HAS, département page HAS, début, fin, source)
CT = [
 ("Didier","Lepelletier","président (depuis 17/09/2026)","membre du collège de la HAS","", "2026-09-17", D1, U_CT),
 ("Pierre","Cochat","ancien président (mandat terminé juillet 2026)","pédiatrie / néphrologie (non confirmé par la page)","", "2020-08-20","2026-07-31","https://www.has-sante.fr/jcms/p_4472504/fr/le-pr-didier-lepelletier-nomme-president-de-la-commission-de-la-transparence-ct"),
 ("Etienne","Lengliné","vice-président titulaire","hématologie","75",D0,D1,U_CT),
 ("Francis","Bonnet","vice-président titulaire","anesthésie-réanimation","75",D0,D1,U_CT),
 ("Michel","Clanet","ancien vice-président titulaire (démission mars 2026)","neurologie (non confirmé)","", D0,"2026-03-12",U_CT26a),
 ("Elisabeth","Aslangul","titulaire","médecine interne et infectiologie","92",D0,D1,U_CT),
 ("Vincent","Audigier","titulaire","cardiologie","69","2026-05-13",D1,U_CT26c),
 ("François-Jérôme","Authier","titulaire","neurologie","94","2026-05-13",D1,U_CT26c),
 ("Fatiha","Barka","titulaire (usagers)","association de malades et d'usagers","33",D0,D1,U_CT),
 ("Audrey","Bellesoeur","suppléante","oncologie","75",D0,D1,U_CT),
 ("Hugues","Blondon","titulaire","hépato-gastroentérologie","78",D0,D1,U_CT),
 ("Sylvie","Chevret","titulaire","biostatistiques et méthodologie","75",D0,D1,U_CT),
 ("Muriel","Doret-Dion","titulaire","gynécologie-obstétrique","69",D0,D1,U_CT),
 ("Céline","Eiden","titulaire","pharmacologie","34",D0,D1,U_CT),
 ("Patricia","Etienne","suppléante puis titulaire (03/2026)","médecine générale","30",D0,D1,U_CT),
 ("Thierry","Facon","titulaire","hématologie","59",D0,D1,U_CT),
 ("Raphaël","Favory","titulaire","anesthésie-réanimation et thérapeutique","59",D0,D1,U_CT),
 ("Jean-Christophe","Lega","titulaire","thérapeutique et médecine interne","69",D0,D1,U_CT),
 ("Christophe","Leroyer","suppléant","pneumologie","29","2025-07-01",D1,U_CT25),
 ("Clara","Locher","titulaire","pharmacologie","35",D0,D1,U_CT),
 ("Ariane","Mallat","titulaire","hépato-gastroentérologie","94",D0,D1,U_CT),
 ("Guillaume","Marie","suppléant","oncologie","62",D0,D1,U_CT),
 ("Véronique","Minard-Colin","titulaire","pédiatrie et oncologie","94",D0,D1,U_CT),
 ("Patrick","Niaudet","titulaire","néphrologie et pédiatrie","75",D0,D1,U_CT),
 ("Anne-Pierre","Pickaert","suppléante (usagers)","association de malades et d'usagers","75",D0,D1,U_CT),
 ("Lionel","Piroth","suppléant","médecine interne et infectiologie","21","2026-06-11",D1,U_CT26b),
 ("Matthieu","Roustit","suppléant","pharmacologie","38",D0,D1,U_CT),
 ("Catherine","Simonin","titulaire (usagers)","association de malades et d'usagers","82",D0,D1,U_CT),
 ("Dominique","Tregourès","titulaire","pharmacie d'officine","78",D0,D1,U_CT),
 ("Albert","Trinh Duc","titulaire","médecine d'urgence","47",D0,D1,U_CT),
 ("Sylvie","Viaux-Savelon","titulaire","pédopsychiatrie","75",D0,D1,U_CT),
 # anciens membres du mandat 2024-2027 (démissions publiées au BO)
 ("Pierre","Attali","ancien titulaire (démission juin 2025)","compétence scientifique médicament","", D0,"2025-06-30",U_CT24),
 ("Marina","Nguenang","ancienne suppléante (démission juin 2025)","compétence scientifique médicament","", D0,"2025-06-30",U_CT24),
 ("Benoit","Pilmis","ancien suppléant (démission juin 2026)","infectiologie (non confirmé)","", D0,"2026-06-11",U_CT24),
 ("Eric","Bonnefoy-Cudraz","ancien titulaire (nommé 07/2025, absent de la liste actuelle)","cardiologie (non confirmé)","", "2025-07-01","",U_CT25),
]
CN = [  # (prénom, nom, rôle, spécialité, dep)
 ("Jean-Yves","Grall","président (membre du collège)","cardiologie","69"),
 ("Françoise","Lucet","vice-présidente","cardiologie","75"),
 ("Nawale","Hajjaji","vice-présidente","cancérologie / oncologie","59"),
 ("Pierre","Ambrosi","membre","cardiologie","13"),
 ("Murielle","Assoun","membre","diététique et nutrition","75"),
 ("Alexander","Balcerac","membre","neurologie","75"),
 ("Catherine","Bancal","membre","pneumologie","75"),
 ("Lucien","Baraza","membre","infirmier","69"),
 ("Frédéric","Barbot","membre","méthodologie handicap et numérique","92"),
 ("Martine","Bouvard","membre","psychologue","73"),
 ("Hervé","Corbineau","membre","chirurgie cardiaque thoracique","35"),
 ("Philippe","Cornu","membre","neurochirurgie","75"),
 ("Eric","De Kerviler","membre","radiologie","75"),
 ("Benoit","Dervaux","membre","statistique - santé publique","59"),
 ("Patrick","Feugier","membre","chirurgie vasculaire","69"),
 ("Delphine","Follet","membre (usagers)","association de malades et d'usagers","59"),
 ("Dominique","Garel","membre (usagers)","association de malades et d'usagers","75"),
 ("Charlotte","Gourio","membre","pharmacie hospitalière","14"),
 ("Marie Paule","Guillodo","membre","néphrologie","29"),
 ("Pascal","Guillon","membre","chirurgie orthopédique et traumatologique","93"),
 ("Sylvie","Joannidis","membre","diabétologie","92"),
 ("Pierre","Lantelme","membre","cardiologie","69"),
 ("Jean-Charles","Mikaelian","membre","urologie","91"),
 ("Jean","Paysant","membre","médecine physique et de réadaptation","54"),
 ("Anne-Marie","Perron","membre (usagers)","association de malades et d'usagers","54"),
 ("Samuel","Pouplin","membre","ergothérapie","92"),
 ("Amina","Rezkallah","membre","ophtalmologie","69"),
 ("Stéphane","Tringali","membre","ORL","69"),
 ("Jean Pierre","Zarski","membre","hépato-gastro entérologie","38"),
]
rows = [dict(commission="CT", prenom=p, nom=n, role=r, specialite=s, dep_has=d, mandat_debut=a, mandat_fin=b, source_url=u)
        for p, n, r, s, d, a, b, u in CT]
rows += [dict(commission="CNEDiMTS", prenom=p, nom=n, role=r, specialite=s, dep_has=d, mandat_debut=C0, mandat_fin=C1, source_url=U_CN)
         for p, n, r, s, d in CN]
M = pd.DataFrame(rows)
if os.environ.get("SUIVRE_MEMBRES_HAS"):   # tests : liste fictive de membres, pour ne jamais associer un vrai nom à de faux montants
    M = pd.read_csv(os.environ["SUIVRE_MEMBRES_HAS"], dtype=str).fillna("")
M.insert(0, "id", range(1, len(M) + 1))
M.to_csv(HAS / "membres_commissions.csv", index=False)
print(len(M), "membres écrits :", M.commission.value_counts().to_dict())

# ---------- Transparence Santé
# Vue nette (commun.vues_ts) : une convention exécutée par des rémunérations ou avantages liés n'est pas recomptée.
con = vues_ts(duckdb.connect())
M["nom_c"] = M.nom.str.upper().map(lambda s: re.sub(r"[^A-Z0-9]", "", __import__("unidecode").unidecode(s)))
M["pre_n"] = M.prenom.map(lambda s: re.sub(r"[^A-Z0-9]+", " ", __import__("unidecode").unidecode(s).upper()).strip())
con.register("m", M[["id", "nom_c", "pre_n"]])
# Vue `prs` (commun.vue_professionnels) : rpps = RPPS valide ou NULL (les identifiants factices ne regroupent personne).
T = con.execute(f"""
 WITH t AS (SELECT replace(nn(identite),' ','') nom_c, nn(prenom) pre_t, identite, prenom, rpps, profession_libelle prof,
        dep, ville, raison_sociale labo, lien_interet lien, montant, cast(coalesce(date, date_debut) AS DATE) d, id ligne
      FROM prs WHERE montant IS NOT NULL)
 SELECT m.id mid, t.* FROM t JOIN m ON t.nom_c=m.nom_c
   AND (t.pre_t=m.pre_n OR split_part(t.pre_t,' ',1)=split_part(m.pre_n,' ',1))""").df()
print(len(T), "lignes TS avec même nom (et prénom compatible)")
T["dt"] = pd.to_datetime(T.d)
T["an"] = T.dt.dt.year
T["dep"] = T.dep.fillna("").astype(str).str.strip()
T["cluster"] = T.rpps.where(T.rpps.notna(), "noid|" + T.dep)

def prof_ok(spec, prof):
    s, p = spec.lower(), (prof or "").lower()
    if "infirmier" in s: return "infirm" in p
    if any(k in s for k in ("pharmacie", "pharmacologie")): return ("pharmac" in p) or ("médecin" in p) or ("medecin" in p)
    if any(k in s for k in ("psychologue", "diététique", "ergothérapie", "usagers", "méthodolog", "statistique", "biostat", "collège")): return True
    return ("médecin" in p) or ("medecin" in p) or ("chirurgien" in p)   # médecins : on écarte p.ex. infirmier, aide-soignant
RANK = {"sûre": 3, "probable": 2, "homonyme possible": 1}
res, det = [], []
for _, mb in M.iterrows():
    g = T[T.mid == mb.id]
    base = dict(id=mb.id, commission=mb.commission, nom=mb.nom, prenom=mb.prenom, role=mb.role, specialite=mb.specialite, dep_has=mb.dep_has,
                mandat_debut=mb.mandat_debut, mandat_fin=mb.mandat_fin, source_url=mb.source_url)
    if g.empty:
        res.append({**base, "trouve_dans_ts": False, "qualite": "absent", "total_recu": 0}); continue
    ncl_rpps = g[g.rpps.notna()].cluster.nunique()
    cls = []
    for key, c in g.groupby("cluster"):
        has_id = c.rpps.notna().all()
        profs = c.prof.dropna().unique()
        pok = any(prof_ok(mb.specialite, p) for p in profs) if len(profs) else True
        if mb.dep_has:
            dep_ok = (c.dep == mb.dep_has).any()
            lvl = ("sûre" if (has_id and len(c) >= 2) else "probable") if dep_ok else "homonyme possible"
        else:
            lvl = "probable" if (has_id and len(c) >= 2 and ncl_rpps == 1) else "homonyme possible"
        if not pok: lvl = {"sûre": "probable", "probable": "homonyme possible"}.get(lvl, lvl)
        cls.append((key, lvl, c))
    # Une seule personne par expert : le meilleur groupe (qualité, RPPS, montant). On n'additionne jamais deux RPPS
    # différents ; seuls s'y ajoutent les versements sans RPPS valide du même département. Si aucun groupe n'est sûr
    # ou probable, aucun total n'est publié : on ne peut pas dire à qui sont ces versements.
    cands = [x for x in cls if x[1] != "homonyme possible"]
    if not cands:
        res.append({**base, "trouve_dans_ts": True, "qualite": "homonyme possible", "nb_personnes_homonymes_ecartees": len(cls),
                    "montant_homonymes_ecartes": round(g.montant.sum())}); continue
    best = max(cands, key=lambda x: (RANK[x[1]], x[2].rpps.notna().all(), x[2].montant.sum(), x[0]))
    deps_best = set(best[2].dep) - {""}
    keep = [best] + [x for x in cands if x is not best and x[0].startswith("noid|") and best[2].rpps.notna().all()
                     and x[0].split("|", 1)[1] in deps_best]
    qual = best[1]
    K = pd.concat([x[2] for x in keep]); D = pd.concat([x[2] for x in cls if not any(x is y for y in keep)]) if len(keep) < len(cls) else T.iloc[0:0]
    K = K.drop_duplicates("ligne")
    deb, fin = pd.Timestamp(mb.mandat_debut), pd.Timestamp(mb.mandat_fin) if mb.mandat_fin else pd.Timestamp("2100-01-01")
    inm = K[(K.dt >= deb) & (K.dt <= fin)]
    hc = K[K.lien != "convention"]
    par_lab = K.groupby("labo").montant.sum().reset_index().sort_values(["montant", "labo"], ascending=[False, True]).set_index("labo").montant
    ans = K.groupby("an").montant.sum()
    r = {**base, "trouve_dans_ts": True, "qualite": qual, "nb_lignes": len(K), "total_recu": round(K.montant.sum()),
         "total_hors_convention": round(hc.montant.sum()),
         "montant_remuneration": round(K[K.lien == "remuneration"].montant.sum()), "montant_convention": round(K[K.lien == "convention"].montant.sum()),
         "montant_avantage": round(K[K.lien == "avantage"].montant.sum()),
         "nb_labos": K.labo.nunique(), "top_labos": " ; ".join(f"{l} ({round(v):,} €)".replace(",", " ") for l, v in par_lab.head(3).items()),
         "premiere_annee": int(K.an.min()), "derniere_annee": int(K.an.max()),
         "pendant_mandat_nb_lignes": len(inm), "pendant_mandat_total": round(inm.montant.sum()),
         "pendant_mandat_hors_convention": round(inm[inm.lien != "convention"].montant.sum()), "pendant_mandat_nb_labos": inm.labo.nunique(),
         "montant_2023_2026": round(K[K.an >= 2023].montant.sum()),
         "rpps": " ; ".join(sorted(K.rpps.dropna().unique())), "professions_ts": " ; ".join(sorted(K.prof.dropna().unique())),
         "villes_ts": " ; ".join((lambda vc: sorted(vc.index, key=lambda v: (-vc[v], v))[:3])(K.ville.dropna().str.upper().value_counts())), "deps_ts": " ; ".join(sorted(set(K.dep) - {""})),
         "nb_personnes_homonymes_ecartees": len(cls) - len(keep), "montant_homonymes_ecartes": round(D.montant.sum()) if len(D) else 0}
    for a in range(2012, 2027): r[f"an_{a}"] = round(ans.get(a, 0))
    res.append(r)
    dl = K.assign(pendant=(K.dt >= deb) & (K.dt <= fin)).groupby("labo").apply(lambda x: pd.Series(dict(
        total=round(x.montant.sum()), total_hors_convention=round(x[x.lien != "convention"].montant.sum()), nb_lignes=len(x),
        pendant_mandat=round(x[x.pendant].montant.sum()), premiere_annee=int(x.an.min()), derniere_annee=int(x.an.max()),
        liens=" / ".join(sorted(x.lien.unique())))), include_groups=False).reset_index().sort_values(["total", "labo"], ascending=[False, True])
    for c_, v in [("commission", mb.commission), ("nom", mb.nom), ("prenom", mb.prenom), ("qualite", qual)][::-1]: dl.insert(0, c_, v)
    det.append(dl)
R = pd.DataFrame(res).sort_values(["total_recu", "id"], ascending=[False, True])
R.to_csv(OUT / "experts_has_versements.csv", index=False)
pd.concat(det).to_csv(OUT / "experts_has_detail_labos.csv", index=False)
f = R[R.trouve_dans_ts]
print(f"\n{len(R)} membres ; {len(f)} retrouvés dans TS ; qualité : {f.qualite.value_counts().to_dict()}")
for q in ("sûre", "probable", "homonyme possible"):
    s = f[f.qualite == q]; print(f"  {q}: {len(s)} membres, {s.total_recu.sum():,.0f} € (hors convention {s.total_hors_convention.sum():,.0f} ; pendant mandat {s.pendant_mandat_total.sum():,.0f})")
print(f[["commission", "nom", "prenom", "role", "qualite", "total_recu", "total_hors_convention", "pendant_mandat_total", "nb_labos", "top_labos"]].head(25).to_string())
