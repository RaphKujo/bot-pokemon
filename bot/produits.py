"""Reconnaît la série, le type et la langue d'un produit à partir de son titre."""
import re
import unicodedata

EXCLUS = [
    "protection", "acrylique", "sleeve", "sleeves", "proteges", "protege", "classeur",
    "portfolio", "album", "vide", "lot", "case", "pack", "giga bundle", "duo",
    "occasion", "abime", "abimee", "defaut", "artset", "pokemon center", "display de deck",
    "display de decks", "display de bundle", "display de bundles", "display bundle",
    "display tripack", "display de tripack", "display de tripacks", "display mini",
    "display blister", "deck", "figurine", "peluche",
]
LANGUES = [
    "japonais", "japonaise", "jap", "jpn", "japanese", "anglais", "anglaise", "eng", "english",
    "chinois", "chinoise", "chinese", "coreen", "coreenne", "korean", "italien", "italienne",
    "ita", "allemand", "allemande", "espagnol", "espagnole", "thai",
]
_TAG_LANGUE = re.compile(r"[\[(]\s*(JAP|JP|JPN|EN|ENG|ANG|ITA|CN|CHN|KR|KOR|DE|ES|PT)\s*[\])]", re.I)


def normaliser(texte):
    """Minuscules, sans accents ni ponctuation : « d'Élite » devient « d elite »."""
    decompose = unicodedata.normalize("NFKD", texte or "")
    sans_accent = "".join(c for c in decompose if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", sans_accent.lower()).split())


def contient(texte_normalise, expression):
    return f" {expression} " in f" {texte_normalise} "


def contient_un(texte_normalise, expressions):
    return any(contient(texte_normalise, e) for e in expressions)


def est_etranger(titre):
    return bool(_TAG_LANGUE.search(titre or "")) or contient_un(normaliser(titre), LANGUES)


def est_exclu(titre):
    t = normaliser(titre).replace("lot de boosters", "bundle").replace("duo de choc", "serie")
    return contient_un(t, EXCLUS)


def type_produit(titre):
    """Renvoie le type d'un produit scellé, ou None si ce n'en est pas un."""
    t = normaliser(titre)
    if contient_un(t, ["demi display", "half display", "18 boosters"]):
        return "demi-display"
    if contient_un(t, ["display", "36 boosters", "booster box"]):
        return "display"
    if contient_un(t, ["etb", "coffret dresseur d elite", "elite trainer"]):
        return "etb"
    if contient_un(t, ["bundle", "6 boosters", "lot de boosters"]):
        return "bundle"
    if contient_un(t, ["tripack", "tri pack", "3 boosters"]):
        return "tripack"
    if contient_un(t, ["ultra premium", "upc"]):
        return "ultra-premium"
    if contient_un(t, ["mini tin", "pokebox", "mini boite"]):
        return "mini-tin"
    if contient_un(t, ["coffret", "collection premium"]):
        return "coffret"
    if contient_un(t, ["booster", "blister"]):
        return "booster"
    return None


def serie_du_titre(titre, series):
    t = normaliser(titre)
    for serie in series:
        if contient_un(t, serie["mots"]) and not contient_un(t, serie.get("exclure", [])):
            return serie
    return None


def reconnaitre(titre, series):
    """Renvoie (serie, type) pour un scellé français suivi, sinon None."""
    if est_etranger(titre) or est_exclu(titre):
        return None
    genre = type_produit(titre)
    serie = serie_du_titre(titre, series)
    return (serie, genre) if genre and serie else None


def reconnaitre_carte(titre, cartes):
    """Renvoie la carte suivie dont le numéro et le nom figurent dans le titre."""
    if est_etranger(titre):
        return None
    t = normaliser(titre)
    for carte in cartes:
        numero = normaliser(str(carte["numero"]))
        if contient(t, numero) and contient(t, normaliser(carte["nom"])):
            etats = [normaliser(e) for e in carte.get("etats", [])]
            if not etats or contient_un(t, etats):
                return carte
    return None
