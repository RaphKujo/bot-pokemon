# Bot Pokémon FR

Le bot vérifie toutes les 5 minutes environ les boutiques configurées. Il t'alerte sur Discord
quand un produit français suivi est disponible au bon prix, et publie une page qui compare
le prix de base au prix vendu. Il ne passe jamais de commande.

## Installation

1. **Discord :** dans ton serveur, ouvre Paramètres du salon > Intégrations > Webhooks.
   Crée un webhook, puis copie son adresse. Ne la partage avec personne.
2. **GitHub :** crée un dépôt public nommé `bot-pokemon`, puis ajoutes-y tous ces fichiers.
   Le dépôt doit rester public pour que les vérifications soient gratuites et illimitées.
3. **Secret :** dans Settings > Secrets and variables > Actions, crée `DISCORD_WEBHOOK_URL`
   et colle l'adresse du webhook.
4. **Test :** dans l'onglet Actions, ouvre Surveillance > Run workflow et coche le diagnostic.
   Le bilan de chaque boutique arrive sur Discord.
5. **Lancement :** relance Run workflow sans cocher le diagnostic, pour créer la page.
6. **Page :** dans Settings > Pages, choisis Deploy from a branch, branche `main`, dossier `/docs`.

## Réglages

- `config/surveillance.yaml` : séries, prix de base, seuil et cartes à l'unité.
- `config/boutiques.yaml` : boutiques, frais de port estimés et pages produit.

## Fonctionnement des alertes

- **Mode `prix` :** alerte à +15 % maximum du prix de base, livraison estimée incluse.
  Pour les boosters et tripacks, le port n'est pas compté, car il se partage dans un panier.
- **Mode `stock` :** alerte à chaque retour en stock. Ajoute `prix_max` à une série pour fixer
  un plafond par type, par exemple `prix_max: {display: 1500}`.
- **Anciennes séries :** toutes les autres séries françaises sont suivies sans plafond. Le premier
  passage est silencieux, puis chaque ajout ou retour en stock déclenche une alerte.
- **Nouvelle alerte :** elle part si une offre revient, ou si son prix baisse d'au moins 5 %.
- **Boutique illisible :** si elle reste inaccessible 30 minutes, le bot te prévient sur Discord.

## Limites

- GitHub peut retarder les vérifications, parfois de plusieurs dizaines de minutes.
  Les stocks qui partent en quelques minutes peuvent donc être manqués.
- Le bot ne contourne aucune protection anti-robot et respecte le fichier robots.txt.
  Une boutique qui refuse l'accès reste simplement non surveillée.
- Les frais de port sont des estimations à remplacer par les vrais tarifs.

## Tests

```
pip install -r requirements.txt pytest
python -m pytest
```
