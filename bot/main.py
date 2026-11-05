"""Un passage de surveillance : lit les boutiques, alerte, enregistre et publie la page."""
import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from . import page, regles, sources
from .discord import Discord

RACINE = Path(__file__).resolve().parent.parent
PARIS = ZoneInfo("Europe/Paris")
DELAI_PANNE = timedelta(minutes=30)
DELAI_SAUVEGARDE = timedelta(minutes=60)


def charger_yaml(chemin):
    return yaml.safe_load(chemin.read_text(encoding="utf-8"))


def charger_etat(chemin):
    if chemin.exists():
        return json.loads(chemin.read_text(encoding="utf-8"))
    return {"boutiques": {}, "offres": {}, "sauvegarde": None}


def empreinte(etat):
    return json.dumps({"b": etat["boutiques"], "o": etat["offres"]}, sort_keys=True)


def traiter_offres(etat, boutique, offres, config, maintenant):
    """Met à jour les offres d'une boutique lue avec succès et renvoie les alertes."""
    info = etat["boutiques"].setdefault(boutique["id"], {})
    connue = bool(info.get("init"))
    alertes, changements = [], []
    vues = set()
    for offre in offres:
        vues.add(offre["id"])
        ancienne = etat["offres"].get(offre["id"])
        offre["compare"] = regles.prix_compare(offre, config)
        offre["alertable"] = regles.est_alertable(offre, config)
        motif = regles.motif_alerte(offre, ancienne, connue, config, maintenant)
        for cle in ("derniere_alerte", "prix_alerte"):
            if ancienne and ancienne.get(cle) is not None:
                offre[cle] = ancienne[cle]
        if motif:
            offre["derniere_alerte"] = maintenant.isoformat()
            offre["prix_alerte"] = offre["prix"]
            alertes.append((offre, motif))
        if not ancienne or (ancienne["prix"], ancienne["dispo"]) != (offre["prix"], offre["dispo"]):
            changements.append(offre)
        etat["offres"][offre["id"]] = offre
    for ident, offre in etat["offres"].items():
        if offre["boutique"] == boutique["id"] and ident not in vues and offre["dispo"] != "retiree":
            offre.update(dispo="retiree", alertable=False)
            changements.append(offre)
    info.update(init=True, ok=True, nb_offres=len(vues), message=None, panne_depuis=None)
    return alertes, changements


def noter_panne(etat, boutique, erreur, maintenant):
    """Enregistre une panne et renvoie un message quand elle dure."""
    info = etat["boutiques"].setdefault(boutique["id"], {})
    info.update(ok=False, message=str(erreur))
    if not info.get("panne_depuis"):
        info["panne_depuis"] = maintenant.isoformat()
    depuis = datetime.fromisoformat(info["panne_depuis"])
    if maintenant - depuis >= DELAI_PANNE and not info.get("panne_signalee"):
        info["panne_signalee"] = True
        return f"{boutique['nom']} ne peut plus être surveillée : {erreur}"
    return None


def noter_retablissement(etat, boutique):
    info = etat["boutiques"].get(boutique["id"], {})
    if info.pop("panne_signalee", None):
        return f"{boutique['nom']} est de nouveau surveillée."
    return None


def ajouter_historique(chemin, changements, maintenant):
    if not changements:
        return
    nouveau = not chemin.exists()
    with chemin.open("a", newline="", encoding="utf-8") as fichier:
        ecrivain = csv.writer(fichier)
        if nouveau:
            ecrivain.writerow(["date", "boutique", "serie", "type", "prix", "total", "dispo", "titre"])
        for o in changements:
            ecrivain.writerow([maintenant.isoformat(timespec="minutes"), o["boutique_nom"], o["suivi_nom"],
                               o["type"], o["prix"], o["total"], o["dispo"], o["titre"]])


def executer(racine, discord, maintenant=None):
    maintenant = maintenant or datetime.now(timezone.utc)
    config = charger_yaml(racine / "config" / "surveillance.yaml")
    reglages = charger_yaml(racine / "config" / "boutiques.yaml")
    chemin_etat = racine / "data" / "etat.json"
    etat = charger_etat(chemin_etat)
    avant = empreinte(etat)
    lecteur = sources.Lecteur(reglages.get("delai_secondes", 2))
    alertes, changements, messages = [], [], []

    for boutique in reglages["boutiques"]:
        if boutique["type"] == "page_produit" and not boutique.get("pages"):
            etat["boutiques"][boutique["id"]] = {"a_configurer": True}
            continue
        try:
            offres = sources.lire_boutique(boutique, lecteur, config, reglages.get("pages_max", 6))
        except (sources.Bloque, sources.Echec) as erreur:
            message = noter_panne(etat, boutique, erreur, maintenant)
            if message:
                messages.append(message)
            continue
        retabli = noter_retablissement(etat, boutique)
        if retabli:
            messages.append(retabli)
        nouvelles, modifiees = traiter_offres(etat, boutique, offres, config, maintenant)
        alertes += nouvelles
        changements += modifiees

    # Si Discord échoue, rien n'est enregistré : le passage suivant renverra l'alerte.
    if alertes:
        discord.alertes(alertes)
    for message in messages:
        discord.message(message)

    derniere = etat.get("sauvegarde")
    expire = not derniere or maintenant - datetime.fromisoformat(derniere) >= DELAI_SAUVEGARDE
    if empreinte(etat) != avant or expire:
        etat["sauvegarde"] = maintenant.isoformat()
        chemin_etat.parent.mkdir(exist_ok=True)
        chemin_etat.write_text(json.dumps(etat, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        ajouter_historique(racine / "data" / "historique.csv", changements, maintenant)
        maj = maintenant.astimezone(PARIS).strftime("%d/%m/%Y à %H:%M")
        (racine / "docs").mkdir(exist_ok=True)
        (racine / "docs" / "index.html").write_text(
            page.generer(etat, config, reglages["boutiques"], maj), encoding="utf-8")
    print(f"{len(alertes)} alerte(s), {len(changements)} changement(s)")
    return alertes


def diagnostic(racine, discord):
    """Teste chaque boutique et envoie le bilan sur Discord, sans toucher à l'état."""
    config = charger_yaml(racine / "config" / "surveillance.yaml")
    reglages = charger_yaml(racine / "config" / "boutiques.yaml")
    lecteur = sources.Lecteur(reglages.get("delai_secondes", 2))
    lignes = ["Diagnostic du bot Pokémon"]
    for boutique in reglages["boutiques"]:
        if boutique["type"] == "page_produit" and not boutique.get("pages"):
            lignes.append(f"⚪ {boutique['nom']} : aucune page produit renseignée")
            continue
        try:
            offres = sources.lire_boutique(boutique, lecteur, config, reglages.get("pages_max", 6))
            lignes.append(f"🟢 {boutique['nom']} : lisible, {len(offres)} offres suivies")
        except (sources.Bloque, sources.Echec) as erreur:
            lignes.append(f"🔴 {boutique['nom']} : {erreur}")
    texte = "\n".join(lignes)
    print(texte)
    discord.message(texte)


def principal():
    parser = argparse.ArgumentParser()
    parser.add_argument("--diagnostic", action="store_true")
    args = parser.parse_args()
    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook:
        sys.exit("Secret DISCORD_WEBHOOK_URL manquant : ajoute-le dans les réglages du dépôt GitHub.")
    discord = Discord(webhook)
    if args.diagnostic:
        diagnostic(RACINE, discord)
    else:
        executer(RACINE, discord)


if __name__ == "__main__":
    principal()
