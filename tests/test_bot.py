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
    assert sources.analyser_page(html) == ("ETB", "59.99", "precommande")


def test_page_sans_prix_est_une_erreur():
    with pytest.raises(sources.Echec):
        sources.analyser_page("<html><body>rien</body></html>")


def test_message_discord_lisible():
    message = embed(offre(), "retour")
    assert "ETB Règne Delta" in message["title"]
    assert any(c["value"] == "55,99 €" for c in message["fields"])


def test_ancienne_serie_alerte_sans_plafond():
    serie = next(s for s in SERIES if s["id"] == "anciennes")
    regle = regles.regle_serie(serie, "display", CONFIG)
    assert regle["seuil"] is None and regle["groupe"]
    o = offre(prix=1850.0, total=1856.9, titre="Display EB08 - Poing de Fusion [FR]", **regle)
    assert regles.motif_alerte(o, None, True, CONFIG, T0) == "nouveau"
    assert "Poing de Fusion" in embed(o, "nouveau")["title"]


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
