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
