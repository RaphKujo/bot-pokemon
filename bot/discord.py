"""Envoie les alertes sur Discord. L'adresse du webhook n'apparaît jamais dans les journaux."""
import time

import requests

COULEURS = {"nouveau": 0x0E8F6E, "retour": 0x0E8F6E, "baisse": 0x3A4FD6}
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


def embed(offre, motif):
    genre = NOMS_TYPES.get(offre["type"], offre["type"])
    dispo = "Précommande" if offre["dispo"] == "precommande" else "En stock"
    nom = offre["titre"] if offre.get("groupe") else f"{genre} {offre['suivi_nom']}"
    champs = [
        {"name": "Prix de base", "value": euros(offre["base"]) if offre.get("base") else "À définir", "inline": True},
        {"name": "Prix vendu", "value": euros(offre["prix"]), "inline": True},
        {"name": "Avec livraison", "value": f"{euros(offre['total'])} (estimé)", "inline": True},
        {"name": "Écart", "value": _ecart(offre), "inline": True},
        {"name": "Disponibilité", "value": dispo, "inline": True},
    ]
    if offre.get("seuil"):
        champs.append({"name": "Ton seuil", "value": euros(offre["seuil"]), "inline": True})
    if offre.get("note"):
        champs.append({"name": "À savoir", "value": offre["note"][:1000]})
    return {
        "title": f"{TITRES[motif]} : {nom}"[:250],
        "url": offre["url"], "color": COULEURS[motif],
        "description": f"{offre['boutique_nom']} · {offre['titre']}"[:1000],
        "fields": champs,
    }


class Discord:
    def __init__(self, webhook, pause=1.0):
        self.webhook = webhook
        self.pause = pause

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
        """liste : couples (offre, motif). Les priorités partent en premier."""
        rang = sorted(liste, key=lambda paire: paire[0]["priorite"] != "haute")
        for debut in range(0, len(rang), 10):
            lot = rang[debut:debut + 10]
            urgent = any(o["priorite"] == "haute" for o, _ in lot)
            self._poster({
                "username": "Bot Pokémon",
                "content": "@everyone Série prioritaire disponible" if urgent else "Offre à regarder",
                "embeds": [embed(o, m) for o, m in lot],
                "allowed_mentions": {"parse": ["everyone"] if urgent else []},
            })
            time.sleep(self.pause)

    def message(self, texte):
        self._poster({"username": "Bot Pokémon", "content": texte[:1900], "allowed_mentions": {"parse": []}})
