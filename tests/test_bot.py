import json
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
import yaml

from bot import main, page, produits, regles, sources
from bot.discord import Discord, embed

RACINE = Path(__file__).resolve().parent.parent
CONFIG = yaml.safe_load((RACINE / "config/surveillance.yaml").read_text(encoding="utf-8"))
SERIES = CONFIG["series"]
T0 = datetime(2026, 11, 6, 8, 0, tzinfo=timezone.utc)


def serie_type(titre):
    r = produits.reconnaitre(titre, SERIES)
    return (r[0]["id"], r[1]) if r else None


@pytest.mark.parametrize("titre,attendu", [
    ("ETB Règne Delta", ("regne-delta", "etb")),
    ("Coffret Dresseur d'Élite ME06 Méga-Évolution Règne Delta", ("regne-delta", "etb")),
    ("Display 36 boosters Règne Delta ME06 en français", ("regne-delta", "display")),
    ("Demi-display 18 boosters Règne Delta", ("regne-delta", "demi-display")),
    ("Booster Bundle 6 boosters Règne Delta ME06", ("regne-delta", "bundle")),
    ("Tripack Otaria Règne Delta ME06", ("regne-delta", "tripack")),
    ("Blister booster Règne Delta ME06", ("regne-delta", "booster")),
    ("Display EB11 - Origine Perdue [FR]", ("origine-perdue", "display")),
    ("Display EB12 - Tempête Argentée [FR]", ("tempete-argentee", "display")),
    ("Bundle EV03.5 - 151 [FR]", ("151", "bundle")),
    ("Bundle EV10.5 - Foudre Noire [FR]", ("foudre-noire", "bundle")),
    ("Bundle EV10.5 - Flamme Blanche [FR]", ("flamme-blanche", "bundle")),
    ("Display Pokémon EB7 Évolution Céleste", ("evolution-celeste", "display")),
    ("ETB Pokémon Destinées de Paldea EV04.5", ("destinees-de-paldea", "etb")),
    ("Display Pokémon Méga-Évolution (ME01) – Boîte de 36 Boosters", ("mega-evolution", "display")),
    ("ETB - Pokemon - Méga-Évolution - ME01 - Scellé - Français", ("mega-evolution", "etb")),
    ("Coffret Dresseur d'élite 30e Anniversaire", ("30-ans", "etb")),
    ("Lot de boosters Pokémon 30 ans", ("30-ans", "bundle")),
    ("COFFRET POKÉMON 30 ANS CÉLÉBRATION DRESSEUR D'ÉLITE", ("30-ans", "etb")),
    ("COLLECTION ULTRA PREMIUM POKÉMON JCC 30TH CELEBRATION NUIT", ("30-ans", "ultra-premium")),
    ("Pokémon – Tripack – Règne Delta – ME06 – 3 boosters – en français", ("regne-delta", "tripack")),
    ("Display EV06 - Mascarade Crépusculaire [FR]", ("anciennes", "display")),
    ("Display EB08 - Poing de Fusion [FR]", ("anciennes", "display")),
    ("Display EV01 - Ecarlate et Violet [FR]", ("anciennes", "display")),
    ("ETB Soleil et Lune Duo de Choc", ("anciennes", "etb")),
    ("Booster Set de Base", ("anciennes", "booster")),
    ("Display Évolutions Prismatiques", ("anciennes", "display")),
])
def test_produits_reconnus(titre, attendu):
    assert serie_type(titre) == attendu


@pytest.mark.parametrize("titre", [
    "Display SV2A - Pokemon 151 [JAP]",
    "Display M2 - Inferno X [JAP]",
    "Display Pokémon M6 Storm Emeralda en chinois traditionnel ME06 Règne delta",
    "ETB Règne Delta avec protection acrylique",
    "Display Règne Delta avec protection acrylique",
    "Artset 4 blisters Règne Delta ME06 avec protection acrylique",
    "Portfolio + 1 booster Règne Delta",
    "Case 10 ETB - Pokemon - Règne Delta - Méga-Rayquaza - ME06",
    "Pokémon – Pack – 1 ETB Règne Delta (ME06) + 2 Tripack Règne Delta (ME06)",
    "Display Bundle 151 scellée",
    "Display mini tins 151",
    "Display EB07 vide",
    "ETB Pokémon Center 151",
    "ETB ME05 Nuit Noire Méga-Évolution",
    "Display ME02 - Flammes Fantasmagoriques [FR]",
    "Bundle ME02.5 - Héros Transcendant [FR]",
    "Display S1V3 - Les Terres d'Encres [FR]",
    "Display OP-13 Successeurs",
    "Display ME02 - Flammes Fantasmagoriques (ME02)",
    "Display ME04 - Chaos Ascendant [FR]",
    "Énergies Méga-Évolution booster",
    "DISPLAY 151 (EN)",
])
def test_produits_ignores(titre):
    assert serie_type(titre) is None


def offre(**autres):
    o = {"id": "k:1", "boutique": "k", "boutique_nom": "Kairyu", "titre": "ETB", "url": "https://x.fr/1",
         "prix": 55.99, "port": 6.9, "total": 62.89, "dispo": "stock", "note": None,
         **regles.regle_serie(SERIES[0], "etb", CONFIG)}
    o.update(autres)
    o["compare"] = regles.prix_compare(o, CONFIG)
    return o


def test_seuil_quinze_pourcent():
    assert regles.regle_serie(SERIES[0], "etb", CONFIG)["seuil"] == 64.39
    assert regles.regle_serie(SERIES[0], "display", CONFIG)["seuil"] == 247.99


def test_port_compte_sur_etb_pas_sur_booster():
    assert regles.est_alertable(offre(total=64.39), CONFIG)
    assert not regles.est_alertable(offre(total=64.40), CONFIG)
    petit = regles.regle_serie(SERIES[0], "booster", CONFIG)
    assert regles.est_alertable({**offre(prix=6.5, total=13.4), **petit}, CONFIG)


def test_rupture_et_trop_cher_sans_alerte():
    assert regles.motif_alerte(offre(dispo="rupture"), None, True, CONFIG, T0) is None
    assert regles.motif_alerte(offre(prix=74.9, total=81.8), None, True, CONFIG, T0) is None


def test_retour_baisse_et_pas_de_doublon():
    ancienne = offre(dispo="rupture", alertable=False)
    assert regles.motif_alerte(offre(), ancienne, True, CONFIG, T0) == "retour"
    deja = offre(alertable=True, prix_alerte=60.0, derniere_alerte=T0.isoformat())
    assert regles.motif_alerte(offre(prix=59.0, total=65), deja, True, CONFIG, T0) is None
    assert regles.motif_alerte(offre(prix=56.0, total=62.9), deja, True, CONFIG, T0) == "baisse"


def test_anti_rebond():
    ancienne = offre(alertable=False, prix_alerte=55.99, derniere_alerte=T0.isoformat())
    assert regles.motif_alerte(offre(), ancienne, True, CONFIG, T0 + timedelta(minutes=20)) is None
    assert regles.motif_alerte(offre(), ancienne, True, CONFIG, T0 + timedelta(minutes=61)) == "retour"


def test_rebond_avec_baisse_realerte():
    ancienne = offre(dispo="rupture", alertable=False, prix_alerte=62.0, derniere_alerte=T0.isoformat())
    assert regles.motif_alerte(offre(prix=55.99), ancienne, True, CONFIG, T0 + timedelta(minutes=10)) == "baisse"


def test_carte_a_l_unite():
    cartes = [{"nom": "Dracaufeu", "numero": "125/197", "prix_max": 60}]
    assert produits.reconnaitre_carte("125/197 - Dracaufeu ex", cartes) == cartes[0]
    assert produits.reconnaitre_carte("126/197 - Dracaufeu ex", cartes) is None
    assert produits.reconnaitre_carte("125/197 - Dracaufeu ex [JAP]", cartes) is None
    assert regles.regle_carte(cartes[0])["seuil"] == 60.0


def test_mode_stock_silencieux_au_premier_passage():
    serie = next(s for s in SERIES if s["id"] == "origine-perdue")
    o = offre(prix=449.9, total=456.8, **regles.regle_serie(serie, "display", CONFIG))
    assert regles.motif_alerte(o, None, False, CONFIG, T0) is None
    assert regles.motif_alerte(o, None, True, CONFIG, T0) == "nouveau"


def test_analyse_page_jsonld():
    html = '''<script type="application/ld+json">{"@graph":[{"@type":"Product","name":"ETB",
    "offers":{"@type":"Offer","price":"59.99","availability":"https://schema.org/PreOrder"}}]}</script>'''
    assert sources.analyser_page(html) == ("ETB", "59.99", "precommande", None)


def test_page_sans_prix_est_une_erreur():
    with pytest.raises(sources.Echec):
        sources.analyser_page("<html><body>rien</body></html>")


def test_message_discord_lisible():
    autre = offre(boutique_nom="LorenZone", prix=74.9, total=81.8, url="https://y.fr/2")
    message = embed(offre(image="https://x.fr/i.png"), "retour", {"autres": [autre], "plus_bas": 50.0}, "https://p.fr/")
    assert "ETB Règne Delta" in message["title"]
    assert message["description"].startswith("**Bon prix**")
    assert message["thumbnail"]["url"] == "https://x.fr/i.png"
    valeurs = {c["name"]: c["value"] for c in message["fields"]}
    assert valeurs["Prix de base"] == "55,99 €" and valeurs["Total"] == "62,89 €"
    assert valeurs["Plus bas relevé"] == "50,00 €" and valeurs["Par booster"] == "environ 6,22 €"
    assert "LorenZone" in valeurs["Ailleurs"] and "cardmarket.com" in valeurs["Liens"]
    assert len(message["fields"]) <= 25


@pytest.mark.parametrize("modif,autres,avis", [
    ({"compare": 56.0}, [], "Excellent prix"),
    ({"compare": 62.0}, [], "Bon prix"),
    ({"compare": 80.0}, [], "Prix élevé"),
    ({"compare": 62.0, "base": 60.0}, [{"compare": 59.0}], "Excellent prix, mais moins cher ailleurs"),
    ({"compare": 400.0, "base": None}, [], "Seule offre trouvée"),
    ({"compare": 400.0, "base": None}, [{"compare": 380.0}], "Une autre boutique est moins chère"),
    ({"compare": 400.0, "base": None}, [{"compare": 420.0}], "Le moins cher trouvé"),
])
def test_verdict(modif, autres, avis):
    assert regles.verdict({**offre(), **modif}, autres)[0] == avis


def test_contexte_compare_les_boutiques():
    etat = {"offres": {
        "a": {"cle": "x", "boutique": "a", "boutique_nom": "A", "dispo": "stock", "compare": 60, "prix": 60, "prix_min": 58},
        "b": {"cle": "x", "boutique": "b", "boutique_nom": "B", "dispo": "stock", "compare": 50, "prix": 50, "prix_min": 50},
        "c": {"cle": "x", "boutique": "c", "boutique_nom": "C", "dispo": "rupture", "compare": 40, "prix": 40, "prix_min": 39},
        "d": {"cle": "y", "boutique": "d", "boutique_nom": "D", "dispo": "stock", "compare": 10, "prix": 10, "prix_min": 10},
    }}
    contexte = main.contexte_offre(etat["offres"]["a"], etat)
    assert [o["boutique"] for o in contexte["autres"]] == ["b"] and contexte["plus_bas"] == 39


def test_cle_serie_groupee():
    serie = next(s for s in SERIES if s["id"] == "anciennes")
    o = {**regles.regle_serie(serie, "display", CONFIG), "titre": "Display EB08 - Poing de Fusion [FR]"}
    assert main.cle_offre(o, CONFIG) == "anciennes:display:poing de fusion"


COTES = [{"nom": "Evolving Skies Booster Box", "trend": 1673.72, "low": 1039},
         {"nom": "Evolving Skies Booster Box (18 Boosters)", "trend": 923.67, "low": 800},
         {"nom": "Evolving Skies Elite Trainer Box [LUJF]", "trend": 462.72, "low": 300},
         {"nom": "Evolving Skies Elite Trainer Box [SEGV]", "trend": 453.17, "low": 300},
         {"nom": "Evolving Skies Pokémon Center Elite Trainer Box [FJUL]", "trend": 1284.6, "low": 900},
         {"nom": "Evolving Skies: Eiscue 3-Pack Blister", "trend": 208.23, "low": 120},
         {"nom": "Evolving Skies Booster", "trend": 34.36, "low": 16.5},
         {"nom": "Evolving Skies Booster (6 Cards)", "trend": 5.02, "low": 5}]


@pytest.mark.parametrize("genre,trend", [
    ("display", 1673.72), ("demi-display", 923.67), ("etb", 453.17), ("tripack", 208.23), ("booster", 34.36), ("coffret", None),
])
def test_cote_trouvee(genre, trend):
    from bot import marche
    cote = marche.cote_pour(COTES, "Evolving Skies", genre)
    assert (cote["trend"] if cote else None) == trend


def test_cote_serie_groupee_et_verdict():
    serie = next(s for s in SERIES if s["id"] == "evolution-celeste")
    o = offre(prix=1500.0, total=1506.9, **regles.regle_serie(serie, "display", CONFIG))
    cote = main.cote_offre(o, COTES, CONFIG)
    assert cote["trend"] == 1673.72
    assert regles.verdict(o, [], cote) == ("Sous la cote du marché", "bon")
    message = embed(o, "retour", {"cote": cote})
    assert message["description"].startswith("**Sous la cote du marché**")
    assert any("1 673,72 €, dès 1 039,00 €" == c["value"] for c in message["fields"])


def test_panne_cotes_ne_bloque_pas(monkeypatch):
    from bot import marche
    monkeypatch.setattr(marche, "charger", lambda: 1 / 0)
    assert main.charger_cotes() == []


def test_assemblage_cotes():
    from bot import marche
    cotes = marche.assembler({"products": [{"idProduct": 1, "name": "Evolving Skies Booster Box"}]},
                             {"priceGuides": [{"idProduct": 1, "trend": 900.0, "avg30": 880.0, "low": 800.0}]})
    assert cotes == [{"id": 1, "nom": "Evolving Skies Booster Box", "trend": 900.0, "avg30": 880.0, "low": 800.0}]


def test_ancienne_serie_alerte_sans_plafond():
    serie = next(s for s in SERIES if s["id"] == "anciennes")
    regle = regles.regle_serie(serie, "display", CONFIG)
    assert regle["seuil"] is None and regle["groupe"]
    o = offre(prix=1850.0, total=1856.9, titre="Display EB08 - Poing de Fusion [FR]", **regle)
    assert regles.motif_alerte(o, None, True, CONFIG, T0) == "nouveau"
    assert "Poing de Fusion" in embed(o, "nouveau")["title"]


def test_lecture_woocommerce():
    produit = {"id": 7, "name": "Pokémon &#8211; Tripack &#8211; Règne Delta &#8211; ME06", "is_in_stock": True,
               "is_purchasable": True, "permalink": "https://x.fr/p", "add_to_cart": {"text": "Ajouter au panier"},
               "prices": {"price": "2199", "currency_minor_unit": 2}}

    class Faux:
        def lire(self, url):
            return type("R", (), {"json": lambda s: [produit]})()

    boutique = {"id": "b", "nom": "B", "url": "https://x.fr", "categories": ["tripack"], "port": 6.9}
    o = sources.lire_woocommerce(boutique, Faux(), CONFIG)[0]
    assert (o["prix"], o["dispo"], o["type"], o["suivi_id"]) == (21.99, "stock", "tripack", "regne-delta")


def _bloc(titre, enseigne, prix, expire=False, ident="1"):
    fin = "price__promotion--expired" if expire else ""
    return (f'<div class="box-corner box-bp"><a class="visite" id="{ident}" href="https://chocobp.com/{ident}">'
            f'<img src="https://cdn.x/i.png"></a><span class="price__promotion {fin}">{prix} €</span>'
            f'<h2 class="box-corner__title">{titre}</h2><div class="box-corner__subtitle">@ {enseigne}'
            f'<span class="payment"></span></div></div>')


def test_flux_bons_plans():
    page_html = (_bloc("[PRÉCOMMANDE] ETB POKÉMON ME06 RÈGNE DELTA", "Amazon", "55.99", ident="1")
                 + _bloc("TRIPACK ME06 RÈGNE DELTA", "Fnac", "17.99", expire=True, ident="2")
                 + _bloc("ETB POKÉMON ME06 RÈGNE DELTA", "Amazon UK", "50.00", ident="3")
                 + _bloc("Display S1V3 - Les Terres d'Encres", "Fnac", "90.00", ident="4"))

    class Faux:
        def lire(self, url):
            return type("R", (), {"text": page_html})()

    boutique = {"id": "choco", "nom": "ChocoBonPlan", "url": "https://x", "port": 0, "port_inconnu": True, "note": "n"}
    offres = sources.lire_flux(boutique, Faux(), CONFIG)
    assert [(o["boutique_nom"], o["type"], o["prix"], o["dispo"]) for o in offres] == [
        ("Amazon", "etb", 55.99, "precommande"), ("Fnac", "tripack", 17.99, "rupture")]
    assert offres[0]["boutique"] == "choco"
    o = {**offres[0], "compare": 55.99}
    valeurs = {c["name"]: c["value"] for c in embed(o, "nouveau")["fields"]}
    assert valeurs["Livraison"] == "À vérifier" and valeurs["À savoir"] == "n"


def test_flux_garde_une_offre_absente_quelques_jours():
    etat = {"boutiques": {"f": {"init": True}}, "offres": {"f:1": {**offre(id="f:1", boutique="f"), "vu": "2026-11-05", "alertable": True}}}
    main.traiter_offres(etat, {"id": "f", "flux_recent": True}, [], CONFIG, T0)
    assert etat["offres"]["f:1"]["dispo"] == "stock"
    main.traiter_offres(etat, {"id": "f", "flux_recent": True}, [], CONFIG, T0 + timedelta(days=8))
    assert etat["offres"]["f:1"]["dispo"] == "retiree"


def test_page_echappe_le_html():
    o = offre(titre="<b>x</b>", boutique_nom="<script>", alertable=True)
    html = page.generer({"offres": {"a": o}, "boutiques": {}}, CONFIG, [{"id": "k", "nom": "K"}], "maintenant")
    assert "<script>" not in html.split("</style>")[1]


# Test complet : fausse boutique et faux Discord sur la machine locale.
ETAT_SERVEUR = {"produits": [], "protege": False, "discord_refuse": False, "recus": []}


class Serveur(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _repondre(self, code, corps, genre="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", genre)
        self.end_headers()
        self.wfile.write(corps.encode())

    def do_GET(self):
        if self.path == "/robots.txt":
            return self._repondre(200, "User-agent: *\nDisallow: /cart\n", "text/plain")
        if ETAT_SERVEUR["protege"]:
            return self._repondre(403, "Just a moment", "text/html")
        return self._repondre(200, json.dumps({"products": ETAT_SERVEUR["produits"]}))

    def do_POST(self):
        taille = int(self.headers["Content-Length"])
        ETAT_SERVEUR["recus"].append(json.loads(self.rfile.read(taille)))
        self._repondre(500 if ETAT_SERVEUR["discord_refuse"] else 204, "")


def produit(prix, dispo=True, titre="ETB Règne Delta ME06 [FR]"):
    return {"id": 1, "title": titre, "handle": "etb", "tags": [], "product_type": "",
            "variants": [{"id": 11, "title": "Default Title", "price": prix, "available": dispo}]}


@pytest.fixture
def banc(tmp_path):
    serveur = HTTPServer(("127.0.0.1", 0), Serveur)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    adresse = f"http://127.0.0.1:{serveur.server_port}"
    (tmp_path / "config").mkdir()
    (tmp_path / "config/surveillance.yaml").write_text(yaml.safe_dump(CONFIG, allow_unicode=True), encoding="utf-8")
    (tmp_path / "config/boutiques.yaml").write_text(yaml.safe_dump({
        "delai_secondes": 0, "boutiques": [{"id": "t", "nom": "Test", "type": "shopify", "url": adresse,
                                            "collections": ["a"], "port": 6.9}]}), encoding="utf-8")
    ETAT_SERVEUR.update(produits=[], protege=False, discord_refuse=False, recus=[])
    yield tmp_path, Discord(f"{adresse}/webhook", pause=0)
    serveur.shutdown()


def test_parcours_complet(banc):
    dossier, discord = banc
    ETAT_SERVEUR["produits"] = [produit("55.99", dispo=False)]
    assert main.executer(dossier, discord, T0) == []

    ETAT_SERVEUR["produits"] = [produit("55.99")]
    assert [m for _, m in main.executer(dossier, discord, T0 + timedelta(minutes=5))] == ["retour"]
    assert "@everyone" in ETAT_SERVEUR["recus"][-1]["content"]
    assert ETAT_SERVEUR["recus"][-1]["username"] == "Bot Pokémon"
    assert main.executer(dossier, discord, T0 + timedelta(minutes=10)) == []

    ETAT_SERVEUR["produits"] = [produit("74.90")]
    assert main.executer(dossier, discord, T0 + timedelta(minutes=15)) == []

    html = (dossier / "docs/index.html").read_text(encoding="utf-8")
    assert "Rien à saisir" in html and "81,80" in html
    assert (dossier / "data/historique.csv").read_text(encoding="utf-8").count("\n") == 4


def test_discord_en_panne_ne_perd_pas_l_alerte(banc):
    dossier, discord = banc
    ETAT_SERVEUR["produits"] = [produit("55.99")]
    ETAT_SERVEUR["discord_refuse"] = True
    with pytest.raises(RuntimeError):
        main.executer(dossier, discord, T0)
    ETAT_SERVEUR["discord_refuse"] = False
    assert len(main.executer(dossier, discord, T0 + timedelta(minutes=5))) == 1


def test_boutique_bloquee_signalee_une_fois_et_offres_conservees(banc):
    dossier, discord = banc
    ETAT_SERVEUR["produits"] = [produit("55.99")]
    main.executer(dossier, discord, T0)
    ETAT_SERVEUR["protege"] = True
    ETAT_SERVEUR["recus"].clear()
    for minutes in (5, 20, 40, 60):
        main.executer(dossier, discord, T0 + timedelta(minutes=minutes))
    pannes = [m for m in ETAT_SERVEUR["recus"] if "ne peut plus" in m.get("content", "")]
    assert len(pannes) == 1
    etat = json.loads((dossier / "data/etat.json").read_text(encoding="utf-8"))
    assert len(etat["offres"]) == 1 and next(iter(etat["offres"].values()))["dispo"] == "stock"
    ETAT_SERVEUR["protege"] = False
    main.executer(dossier, discord, T0 + timedelta(minutes=70))
    assert any("de nouveau surveillée" in m.get("content", "") for m in ETAT_SERVEUR["recus"])


def test_offre_retiree_du_catalogue(banc):
    dossier, discord = banc
    ETAT_SERVEUR["produits"] = [produit("55.99")]
    main.executer(dossier, discord, T0)
    ETAT_SERVEUR["produits"] = []
    main.executer(dossier, discord, T0 + timedelta(minutes=5))
    etat = json.loads((dossier / "data/etat.json").read_text(encoding="utf-8"))
    assert next(iter(etat["offres"].values()))["dispo"] == "retiree"


def test_robots_txt_respecte(banc):
    dossier, _ = banc
    lecteur = sources.Lecteur(0)
    adresse = yaml.safe_load((dossier / "config/boutiques.yaml").read_text())["boutiques"][0]["url"]
    with pytest.raises(sources.Bloque):
        lecteur.lire(f"{adresse}/cart")
