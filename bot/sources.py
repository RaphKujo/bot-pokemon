"""Lit les catalogues des boutiques, sans jamais contourner une protection."""
import json
import time
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from . import produits, regles

ENTETES = {"User-Agent": "BotPokemonPerso/1.0 (alertes de stock, usage personnel)",
           "Accept-Language": "fr-FR,fr;q=0.9"}
MARQUES_BLOCAGE = ["waiting room", "just a moment", "captcha", "cf-chl", "access denied",
                   "robot check", "verify you are human"]


class Bloque(Exception):
    """La boutique refuse l'accès automatique : on n'insiste pas."""


class Echec(Exception):
    """La lecture a échoué pour une raison technique."""


class Lecteur:
    def __init__(self, delai=2):
        self.delai = delai
        self.session = requests.Session()
        self.session.headers.update(ENTETES)
        self.robots = {}

    def autorise(self, url):
        parties = urlsplit(url)
        racine = f"{parties.scheme}://{parties.netloc}"
        if racine not in self.robots:
            analyseur = RobotFileParser()
            try:
                reponse = self.session.get(f"{racine}/robots.txt", timeout=15)
                analyseur.parse(reponse.text.splitlines() if reponse.status_code == 200 else [])
            except requests.RequestException:
                analyseur.parse([])
            self.robots[racine] = analyseur
        return self.robots[racine].can_fetch(ENTETES["User-Agent"], url)

    def lire(self, url):
        if not self.autorise(url):
            raise Bloque("adresse interdite par le fichier robots.txt")
        time.sleep(self.delai)
        try:
            reponse = self.session.get(url, timeout=20)
        except requests.RequestException as erreur:
            raise Echec(type(erreur).__name__) from None
        debut = reponse.text[:4000].lower()
        if reponse.status_code in (401, 403, 429, 503):
            raise Bloque(f"accès refusé (code {reponse.status_code})")
        if reponse.status_code >= 400:
            raise Echec(f"code {reponse.status_code}")
        if any(marque in debut for marque in MARQUES_BLOCAGE):
            raise Bloque("page de protection anti-robot")
        return reponse


def _nouvelle_offre(boutique, regle, identifiant, titre, url, prix, dispo):
    prix = round(float(prix), 2)
    franco = boutique.get("franco")
    port = 0.0 if franco is not None and prix >= franco else float(boutique.get("port", 0))
    return {
        "id": f"{boutique['id']}:{identifiant}", "boutique": boutique["id"],
        "boutique_nom": boutique["nom"], "titre": titre, "url": url,
        "prix": prix, "port": port, "total": round(prix + port, 2), "dispo": dispo,
        "note": boutique.get("note_precommande") if dispo == "precommande" else None,
        **regle,
    }


def _est_precommande(produit, variante):
    texte = " ".join([produit.get("title", ""), variante.get("title", ""),
                      produit.get("product_type", ""), " ".join(_tags(produit))])
    t = produits.normaliser(texte)
    return produits.contient_un(t, ["precommande", "pre commande", "preco", "precommandes",
                                    "pre order", "preorder"])


def _tags(produit):
    tags = produit.get("tags") or []
    return tags.split(",") if isinstance(tags, str) else tags


def _catalogue_shopify(boutique, lecteur, collections, pages_max):
    chemins = [f"/collections/{c}/products.json" for c in collections] or ["/products.json"]
    vus = {}
    for chemin in chemins:
        for page in range(1, pages_max + 1):
            url = f"{boutique['url'].rstrip('/')}{chemin}?limit=250&page={page}"
            try:
                lot = lecteur.lire(url).json().get("products", [])
            except ValueError:
                raise Echec("catalogue illisible : la boutique n'expose pas ce flux") from None
            for produit in lot:
                vus[produit["id"]] = produit
            if len(lot) < 250:
                break
    return vus.values()


def lire_shopify(boutique, lecteur, config, pages_max=6):
    cartes = config.get("cartes") or []
    collections = list(boutique.get("collections") or [])
    if cartes:
        collections += boutique.get("collections_cartes") or []
    offres = []
    for produit in _catalogue_shopify(boutique, lecteur, collections, pages_max):
        for variante in produit.get("variants", []):
            nom_variante = variante.get("title", "")
            titre = produit["title"]
            if nom_variante and nom_variante.lower() != "default title":
                titre = f"{titre} ({nom_variante})"
            carte = produits.reconnaitre_carte(titre, cartes)
            if carte:
                regle = regles.regle_carte(carte)
            else:
                trouve = produits.reconnaitre(titre, config["series"])
                if not trouve:
                    continue
                regle = regles.regle_serie(trouve[0], trouve[1], config)
            if not variante.get("available", False):
                dispo = "rupture"
            else:
                dispo = "precommande" if _est_precommande(produit, variante) else "stock"
            url = f"{boutique['url'].rstrip('/')}/products/{produit['handle']}?variant={variante['id']}"
            offres.append(_nouvelle_offre(boutique, regle, variante["id"], titre, url,
                                          variante["price"], dispo))
    return offres


def _blocs_jsonld(soupe):
    for balise in soupe.find_all("script", type="application/ld+json"):
        try:
            donnees = json.loads(balise.string or "")
        except ValueError:
            continue
        pile = donnees if isinstance(donnees, list) else [donnees]
        while pile:
            bloc = pile.pop()
            if isinstance(bloc, dict):
                if "@graph" in bloc:
                    pile.extend(bloc["@graph"])
                yield bloc


def _est_produit(bloc):
    genre = bloc.get("@type")
    return "Product" in genre if isinstance(genre, list) else genre == "Product"


def analyser_page(html):
    """Extrait titre, prix et disponibilité d'une fiche produit."""
    soupe = BeautifulSoup(html, "html.parser")
    for bloc in _blocs_jsonld(soupe):
        if not _est_produit(bloc):
            continue
        offre = bloc.get("offers") or {}
        offre = offre[0] if isinstance(offre, list) and offre else offre
        prix = offre.get("price") or offre.get("lowPrice")
        if prix is None:
            continue
        etat = str(offre.get("availability", "")).lower()
        if "preorder" in etat or "presale" in etat:
            dispo = "precommande"
        elif "instock" in etat or "limitedavailability" in etat:
            dispo = "stock"
        else:
            dispo = "rupture"
        return bloc.get("name"), str(prix).replace(",", "."), dispo
    raise Echec("prix introuvable sur la page")


def lire_pages(boutique, lecteur, config):
    series = {s["id"]: s for s in config["series"]}
    offres = []
    for page in boutique.get("pages") or []:
        regle = regles.regle_serie(series[page["serie"]], page["type"], config)
        titre, prix, dispo = analyser_page(lecteur.lire(page["url"]).text)
        titre = titre or f"{regle['type']} {regle['suivi_nom']}"
        offres.append(_nouvelle_offre(boutique, regle, page["url"], titre, page["url"], prix, dispo))
    return offres


def lire_boutique(boutique, lecteur, config, pages_max=6):
    if boutique["type"] == "shopify":
        return lire_shopify(boutique, lecteur, config, pages_max)
    return lire_pages(boutique, lecteur, config)
