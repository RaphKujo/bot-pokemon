"""Génère la page de suivi : prix de base, prix vendu et offres à saisir."""
from html import escape
from urllib.parse import urlsplit

from .discord import NOMS_TYPES, euros
from .regles import DISPONIBLE

ORDRE_TYPES = ["display", "demi-display", "etb", "bundle", "tripack", "booster",
               "coffret", "mini-tin", "ultra-premium", "carte"]
ETATS = {"stock": "En stock", "precommande": "Précommande", "rupture": "Rupture", "retiree": "Retiré"}

CSS = """
:root{--fond:#e9ecfa;--feuille:#f9faff;--encre:#1c1f52;--doux:#555a8c;--trait:#cfd4ef;
--bon:#0a7458;--moyen:#99530a;--cher:#ad1e4c;--rail:#d8dcf3;
--foil:linear-gradient(100deg,#6fdcc8,#a5b4ff,#f0a3df,#ffd68a,#6fdcc8)}
@media (prefers-color-scheme:dark){:root{--fond:#14163a;--feuille:#1d2050;--encre:#eef0ff;
--doux:#aeb3dd;--trait:#363a78;--bon:#58d6b1;--moyen:#f0b869;--cher:#ff8fb1;--rail:#343872}}
*{box-sizing:border-box}
body{margin:0;background:var(--fond);color:var(--encre);
font:17px/1.5 "Instrument Sans",system-ui,sans-serif;font-variant-numeric:tabular-nums}
main{max-width:1000px;margin:0 auto;padding:40px 24px 64px}
h1,h2{font-family:"Bricolage Grotesque",system-ui,sans-serif;line-height:1.05;margin:0}
h1{font-size:clamp(2.6rem,8vw,4.8rem);font-weight:800;letter-spacing:-.03em;max-width:13ch}
.maj{color:var(--doux);margin:14px 0 0}
.saisir{margin:32px 0 0;padding:0;list-style:none;display:grid;gap:12px}
.saisir li{background:var(--feuille);padding:16px 18px;border-radius:14px;
border-left:10px solid transparent;border-image:var(--foil) 1;
display:grid;grid-template-columns:1fr auto;gap:4px 18px;align-items:center}
.saisir strong{font-size:1.15rem}
.saisir .prix{font-size:1.5rem;font-weight:700;text-align:right}
.saisir small{color:var(--doux);font-size:.92rem;font-weight:500}
section{margin-top:52px}
h2{font-size:1.9rem;font-weight:700}
.sous{color:var(--doux);margin:6px 0 14px}
.ligne{display:grid;grid-template-columns:130px 1fr 120px 170px;gap:16px;align-items:center;
padding:13px 0;border-top:1px solid var(--trait)}
.nom{font-weight:600}
.ligne.libre{grid-template-columns:1fr 120px 170px}
.vendu{font-weight:700;font-size:1.12rem;text-align:right}
.vendu small{display:block;font-weight:500;font-size:.86rem}
.bon{color:var(--bon)}.moyen{color:var(--moyen)}.cher{color:var(--cher)}.vide{color:var(--doux);font-weight:500}
.ou{font-size:.95rem}
a{color:inherit;text-underline-offset:3px}
a:focus-visible{outline:3px solid var(--doux);outline-offset:2px;border-radius:3px}
.jauge{position:relative;height:30px}
.rail{position:absolute;left:0;right:0;top:11px;height:8px;border-radius:4px;background:var(--rail)}
.zone{position:absolute;top:8px;height:14px;border-radius:3px;background:var(--foil)}
.repere{position:absolute;top:24px;font-size:.74rem;color:var(--doux);transform:translateX(-50%);white-space:nowrap;line-height:1}
.point{position:absolute;top:6px;width:18px;height:18px;margin-left:-9px;border-radius:50%;
background:var(--encre);border:3px solid var(--feuille)}
.texte{color:var(--doux);font-size:.95rem}
details{grid-column:1/-1;font-size:.95rem;color:var(--doux)}
summary{cursor:pointer;width:max-content;max-width:100%}
details ul{margin:8px 0 0;padding-left:18px}
.boutiques{display:grid;grid-template-columns:1fr 2fr;gap:6px 20px;margin:12px 0 0}
.boutiques dt{font-weight:600}.boutiques dd{margin:0;color:var(--doux)}
@media (max-width:720px){body{font-size:16px}main{padding:28px 16px 48px}
.ligne,.ligne.libre{grid-template-columns:1fr auto;gap:6px 12px}.nom{grid-area:1/1}.vendu{grid-area:1/2}.jauge,.ou,.texte.seule{grid-column:1/-1}
.saisir li{grid-template-columns:1fr}.saisir .prix{text-align:left}.boutiques{grid-template-columns:1fr}.boutiques dd{margin-bottom:8px}}
"""


def _lien(url):
    return escape(url, quote=True) if urlsplit(url).scheme in ("http", "https") else "#"


def _ton(offre):
    if offre is None or not offre.get("base"):
        return "vide"
    if offre["alertable"]:
        return "bon"
    return "moyen" if offre["compare"] <= offre["base"] * 1.3 else "cher"


def _jauge(base, seuil, offre):
    if not base:
        return '<div class="texte seule">Prix de base à définir</div>'
    minimum, maximum = base * 0.85, base * 1.6
    pos = lambda v: round(max(0, min(100, (v - minimum) / (maximum - minimum) * 100)), 1)
    fin = seuil or base
    point = f'<span class="point" style="left:{pos(offre["compare"])}%"></span>' if offre else ""
    return (f'<div class="jauge" aria-hidden="true"><span class="rail"></span>'
            f'<span class="zone" style="left:{pos(base)}%;width:{round(pos(fin) - pos(base), 1)}%"></span>'
            f'{point}<span class="repere" style="left:{pos(base)}%">{euros(base)}</span>'
            f'<span class="repere" style="left:{pos(fin)}%">{euros(fin)}</span></div>')


def _ligne(genre, base, seuil, offres):
    dispos = [o for o in offres if o["dispo"] in DISPONIBLE]
    meilleure = min(dispos, key=lambda o: o["compare"], default=None)
    nom = NOMS_TYPES.get(genre, genre)
    if meilleure:
        ecart = ""
        if base:
            ecart = f"<small>{meilleure['compare'] / base * 100 - 100:+.0f} %</small>"
        vendu = f'<div class="vendu {_ton(meilleure)}">{euros(meilleure["compare"])}{ecart}</div>'
        ou = (f'<div class="ou"><a href="{_lien(meilleure["url"])}">{escape(meilleure["boutique_nom"])}</a>'
              f' <span class="texte">{ETATS[meilleure["dispo"]].lower()}</span></div>')
    else:
        vendu = '<div class="vendu vide">Indisponible</div>'
        ou = f'<div class="ou texte">{"Aucune offre trouvée" if not offres else "En rupture partout"}</div>'
    detail = ""
    if len(offres) > 1:
        lignes = "".join(
            f'<li><a href="{_lien(o["url"])}">{escape(o["boutique_nom"])}</a> : {euros(o["prix"])}, '
            f'{ETATS.get(o["dispo"], o["dispo"]).lower()}</li>'
            for o in sorted(offres, key=lambda o: o["prix"]))
        detail = f"<details><summary>Voir les {len(offres)} offres</summary><ul>{lignes}</ul></details>"
    return (f'<div class="ligne"><div class="nom">{escape(nom)}</div>{_jauge(base, seuil, meilleure)}'
            f'{vendu}{ou}{detail}</div>')


def _section_groupee(serie, offres):
    dispos = sorted((o for o in offres if o["dispo"] in DISPONIBLE), key=lambda o: o["titre"])
    lignes = "".join(
        f'<div class="ligne libre"><div class="nom">{escape(o["titre"])}</div>'
        f'<div class="vendu">{euros(o["prix"])}</div>'
        f'<div class="ou"><a href="{_lien(o["url"])}">{escape(o["boutique_nom"])}</a> '
        f'<span class="texte">{ETATS[o["dispo"]].lower()}</span></div></div>'
        for o in dispos)
    corps = lignes or '<p class="texte">Aucune offre en stock pour le moment.</p>'
    return (f'<section><h2>{escape(serie["nom"])}</h2>'
            f'<p class="sous">Alerte à chaque ajout ou retour en stock</p>{corps}</section>')


def _section(serie, offres, config):
    if serie.get("groupe"):
        return _section_groupee(serie, offres)
    types = set(serie.get("prix_base") or {}) | {o["type"] for o in offres}
    lignes = []
    for genre in sorted(types, key=lambda t: ORDRE_TYPES.index(t) if t in ORDRE_TYPES else 99):
        lot = [o for o in offres if o["type"] == genre]
        base = (serie.get("prix_base") or {}).get(genre)
        plafond = (serie.get("prix_max") or {}).get(genre)
        seuil = plafond or (round(base * (1 + config["seuil_pct"] / 100), 2) if base else None)
        lignes.append(_ligne(genre, base, seuil, lot))
    if serie["mode"] == "stock":
        sous = "Alerte à chaque retour en stock"
    else:
        sous = f"Alerte jusqu'à +{config['seuil_pct']} % du prix de base"
    if serie.get("priorite") == "haute":
        sous = f"Prioritaire. {sous}"
    code = f" {escape(serie['code'])}" if serie.get("code") else ""
    corps = "".join(lignes) or '<p class="texte">Aucune offre trouvée pour le moment.</p>'
    return (f'<section><h2>{escape(serie["nom"])}{code}</h2><p class="sous">{sous}</p>{corps}</section>')


def _etat_boutique(info):
    if info is None:
        return "Pas encore vérifiée"
    if info.get("a_configurer"):
        return "Ajoute l'adresse des produits à suivre pour l'activer"
    if info.get("ok"):
        return f"Fonctionne, {info.get('nb_offres', 0)} offres suivies"
    return f"Illisible : {info.get('message', 'erreur inconnue')}"


def generer(etat, config, boutiques, maj):
    offres = list(etat["offres"].values())
    a_saisir = sorted((o for o in offres if o.get("alertable")),
                      key=lambda o: (o["priorite"] != "haute", o["compare"]))
    if a_saisir:
        total = len(a_saisir)
        titre = f"{total} offre{'s' if total > 1 else ''} à saisir"
    else:
        titre = "Rien à saisir pour l'instant"
    cartes = "".join(
        f'<li><div><strong><a href="{_lien(o["url"])}">{escape(NOMS_TYPES.get(o["type"], o["type"]))} '
        f'{escape(o["suivi_nom"])}</a></strong><br><small>{escape(o["boutique_nom"])}, '
        f'{ETATS[o["dispo"]].lower()}{". " + escape(o["note"]) if o.get("note") else ""}</small></div>'
        f'<div class="prix">{euros(o["compare"])}'
        f'{"<br><small>base " + euros(o["base"]) + "</small>" if o.get("base") else ""}</div></li>'
        for o in a_saisir)
    bloc = f'<ul class="saisir">{cartes}</ul>' if cartes else ""
    series = sorted(config["series"], key=lambda s: s.get("priorite") != "haute")
    sections = "".join(_section(s, [o for o in offres if o["suivi_id"] == s["id"]], config) for s in series)
    pieces_cartes = sorted({o["suivi_id"] for o in offres if o["type"] == "carte"})
    for ident in pieces_cartes:
        lot = [o for o in offres if o["suivi_id"] == ident]
        sections += (f'<section><h2>{escape(lot[0]["suivi_nom"])}</h2>'
                     f'{_ligne("carte", None, lot[0]["seuil"], lot)}</section>')
    etat_boutiques = "".join(
        f'<dt>{escape(b["nom"])}</dt><dd>{escape(_etat_boutique(etat["boutiques"].get(b["id"])))}</dd>'
        for b in boutiques)
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Prix Pokémon FR</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,700;12..96,800&family=Instrument+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>{CSS}</style></head>
<body><main><p class="maj"><a href="classeur.html">Ouvrir mon classeur</a></p><h1>{titre}</h1>
<p class="maj">Prix mis à jour le {escape(maj)}. Livraison estimée incluse sur les gros produits.</p>
{bloc}{sections}
<section><h2>Boutiques</h2><dl class="boutiques">{etat_boutiques}</dl></section>
</main></body></html>
"""
