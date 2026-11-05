"""Cote de marché des produits scellés, depuis les fichiers publics de Cardmarket."""
import requests

BASE = "https://downloads.s3.cardmarket.com/productCatalog"
PRODUITS = f"{BASE}/productList/products_nonsingles_6.json"
PRIX = f"{BASE}/priceGuide/price_guide_6.json"


def telecharger(url):
    reponse = requests.get(url, timeout=60, headers={"User-Agent": "BotPokemonPerso/1.0"})
    reponse.raise_for_status()
    return reponse.json()


def assembler(produits, prix):
    """Renvoie une liste de {nom, id, trend, avg30, low}."""
    cotes = {p.get("idProduct"): p for p in prix.get("priceGuides", [])}
    resultat = []
    for produit in produits.get("products", []):
        cote = cotes.get(produit.get("idProduct"), {})
        resultat.append({"id": produit.get("idProduct"), "nom": produit.get("name", ""),
                         "trend": cote.get("trend"), "avg30": cote.get("avg30"), "low": cote.get("low")})
    return resultat


def charger():
    return assembler(telecharger(PRODUITS), telecharger(PRIX))


def _mini(candidats):
    """Garde la version la moins chère quand un produit existe en plusieurs illustrations."""
    avec_prix = [c for c in candidats if c.get("trend")]
    return min(avec_prix, key=lambda c: c["trend"], default=None)


def cote_pour(cotes, en, genre):
    """Retrouve la cote d'un produit à partir du nom anglais de sa série."""
    if not en:
        return None
    if genre == "display":
        return _mini([c for c in cotes if c["nom"] == f"{en} Booster Box"])
    if genre == "demi-display":
        return _mini([c for c in cotes if c["nom"] == f"{en} Booster Box (18 Boosters)"])
    if genre == "bundle":
        return _mini([c for c in cotes if c["nom"] == f"{en} Booster Bundle"])
    if genre == "booster":
        return _mini([c for c in cotes if c["nom"] == f"{en} Booster"])
    if genre == "etb":
        return _mini([c for c in cotes if c["nom"] == f"{en} Elite Trainer Box"
                      or c["nom"].startswith(f"{en} Elite Trainer Box [")])
    if genre == "tripack":
        return _mini([c for c in cotes if c["nom"].startswith(f"{en}: ") and c["nom"].endswith("3-Pack Blister")])
    return None
