"""Décide si une offre mérite une alerte. Aucune requête réseau ici."""
from datetime import datetime, timedelta

DISPONIBLE = {"stock", "precommande"}


def regle_serie(serie, genre, config):
    base = (serie.get("prix_base") or {}).get(genre)
    plafond = (serie.get("prix_max") or {}).get(genre)
    if plafond is not None:
        seuil = float(plafond)
    elif base is not None and serie["mode"] == "prix":
        seuil = round(base * (1 + config["seuil_pct"] / 100), 2)
    else:
        seuil = None
    return {
        "suivi_id": serie["id"], "suivi_nom": serie["nom"], "code": serie.get("code"),
        "priorite": serie.get("priorite", "normale"), "mode": serie["mode"],
        "type": genre, "base": base, "seuil": seuil, "groupe": bool(serie.get("groupe")),
    }


def regle_carte(carte):
    plafond = carte.get("prix_max")
    return {
        "suivi_id": f"carte-{carte['numero']}", "suivi_nom": f"{carte['nom']} {carte['numero']}",
        "code": None, "priorite": carte.get("priorite", "normale"),
        "mode": "prix" if plafond is not None else "stock",
        "type": "carte", "base": None, "seuil": float(plafond) if plafond is not None else None,
    }


def prix_compare(offre, config):
    """Prix comparé au seuil : port inclus, sauf pour les petits achats."""
    return offre["prix"] if offre["type"] in config["types_sans_port"] else offre["total"]


def est_alertable(offre, config):
    if offre["dispo"] not in DISPONIBLE:
        return False
    seuil = offre["seuil"]
    if offre["mode"] == "stock":
        return seuil is None or prix_compare(offre, config) <= seuil
    return seuil is not None and prix_compare(offre, config) <= seuil


def motif_alerte(offre, ancienne, boutique_connue, config, maintenant):
    """Renvoie le motif de l'alerte ou None."""
    if not est_alertable(offre, config):
        return None
    if ancienne is None:
        return "nouveau" if boutique_connue or offre["mode"] == "prix" else None

    derniere = ancienne.get("derniere_alerte")
    prix_alerte = ancienne.get("prix_alerte")
    if prix_alerte and offre["prix"] <= prix_alerte * (1 - config["baisse_min_pct"] / 100):
        return "baisse"
    if ancienne.get("alertable"):
        return None
    if derniere:
        attente = timedelta(minutes=config["anti_rebond_minutes"])
        if maintenant - datetime.fromisoformat(derniere) < attente and offre["prix"] >= (prix_alerte or 0):
            return None
    return "retour"
