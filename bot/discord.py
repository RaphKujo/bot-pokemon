"""Envoie les alertes sur Discord. L'adresse du webhook n'apparaît jamais dans les journaux."""
import time

import requests

from urllib.parse import quote

from . import regles

COULEURS = {"bon": 0x0E8F6E, "moyen": 0xD08A1D, "cher": 0xC2255C}
TITRES = {"nouveau": "Nouvelle offre", "retour": "Disponible", "baisse": "Baisse de prix"}
NOMS_TYPES = {"etb": "ETB", "display": "Display", "demi-display": "Demi-display",
              "bundle": "Bundle", "tripack": "Tripack", "booster": "Booster",
              "coffret": "Coffret", "mini-tin": "Mini-tin", "ultra-premium": "Ultra-Premium",
              "carte": "Carte"}


def euros(valeur):
    return f"{valeur:,.2f} €".replace(",", " ").replace(".", ",")


def _ecart(offre):
    if not offre.get("base"):
        return "Prix de base à définir"
    pct = (offre["compare"] / offre["base"] - 1) * 100
    return f"{pct:+.1f} %".replace(".", ",")


def _nettoyer(texte):
    return str(texte).replace("[", "(").replace("]", ")")


def embed(offre, motif, contexte=None, page_suivi=None):
    contexte = contexte or {}
    autres = contexte.get("autres", [])
    genre = NOMS_TYPES.get(offre["type"], offre["type"])
    dispo = "Précommande" if offre["dispo"] == "precommande" else "En stock"
    nom = offre["titre"] if offre.get("groupe") else f"{genre} {offre['suivi_nom']}"
    avis, ton = regles.verdict(offre, autres)
    port = "Offerte" if offre["port"] == 0 else f"{euros(offre['port'])} (estimé)"
    champs = [
        {"name": "Prix vendu", "value": euros(offre["prix"]), "inline": True},
        {"name": "Livraison", "value": port, "inline": True},
        {"name": "Total", "value": euros(offre["total"]), "inline": True},
    ]
    if offre.get("base"):
        champs += [{"name": "Prix de base", "value": euros(offre["base"]), "inline": True},
                   {"name": "Écart", "value": _ecart(offre), "inline": True}]
    if offre.get("seuil"):
        champs.append({"name": "Ton seuil", "value": euros(offre["seuil"]), "inline": True})
    nombre = regles.BOOSTERS.get(offre["type"])
    if nombre and nombre > 1:
        champs.append({"name": "Par booster", "value": f"environ {euros(offre['prix'] / nombre)}", "inline": True})
    champs.append({"name": "Disponibilité", "value": dispo, "inline": True})
    if contexte.get("plus_bas") and contexte["plus_bas"] < offre["prix"]:
        champs.append({"name": "Plus bas relevé", "value": euros(contexte["plus_bas"]), "inline": True})
    if autres:
        lignes = [f"[{_nettoyer(o['boutique_nom'])}]({o['url']}) : {euros(o['prix'])}" for o in autres[:3]]
        champs.append({"name": "Ailleurs", "value": "\n".join(lignes)[:1000]})
    if offre.get("note"):
        champs.append({"name": "À savoir", "value": offre["note"][:1000]})
    recherche = quote(offre["titre"] if offre.get("groupe") else nom)
    liens = [f"[Acheter chez {_nettoyer(offre['boutique_nom'])}]({offre['url']})",
             f"[Comparer sur Cardmarket](https://www.cardmarket.com/fr/Pokemon/Products/Search?searchString={recherche})"]
    if page_suivi:
        liens.append(f"[Page de suivi]({page_suivi})")
    champs.append({"name": "Liens", "value": "\n".join(liens)})
    message = {
        "title": f"{TITRES[motif]} : {nom}"[:250],
        "url": offre["url"], "color": COULEURS[ton],
        "description": f"**{avis}**\n{offre['boutique_nom']} : {offre['titre']}"[:1000],
        "fields": champs,
    }
    if offre.get("image"):
        message["thumbnail"] = {"url": offre["image"]}
    return message


class Discord:
    def __init__(self, webhook, pause=1.0, page_suivi=None):
        self.webhook = webhook
        self.pause = pause
        self.page_suivi = page_suivi

    def _poster(self, charge):
        for _ in range(3):
            try:
                reponse = requests.post(self.webhook, json=charge, timeout=20)
            except requests.RequestException as erreur:
                raise RuntimeError(f"Discord injoignable ({type(erreur).__name__})") from None
            if reponse.status_code == 429:
                time.sleep(float(reponse.headers.get("Retry-After", 2)))
                continue
            if reponse.status_code >= 300:
                raise RuntimeError(f"Discord a répondu {reponse.status_code}")
            return
        raise RuntimeError("Discord limite trop les envois")

    def alertes(self, liste):
        """liste : (offre, motif) ou (offre, motif, contexte). Les priorités partent en premier."""
        rang = sorted(liste, key=lambda element: element[0]["priorite"] != "haute")
        for debut in range(0, len(rang), 10):
            lot = rang[debut:debut + 10]
            urgent = any(e[0]["priorite"] == "haute" for e in lot)
            self._poster({
                "username": "Bot Pokémon",
                "content": "@everyone Série prioritaire disponible" if urgent else "Offre à regarder",
                "embeds": [embed(*e[:3], page_suivi=self.page_suivi) for e in lot],
                "allowed_mentions": {"parse": ["everyone"] if urgent else []},
            })
            time.sleep(self.pause)

    def message(self, texte):
        self._poster({"username": "Bot Pokémon", "content": texte[:1900], "allowed_mentions": {"parse": []}})
