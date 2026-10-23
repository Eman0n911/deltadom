# DeltaDOM

[中文](README.md) · [English](README.en.md) · [日本語](README.ja.md) · [Français](README.fr.md)

![Illustration conceptuelle : le curseur reste relié au ticket visé tandis que les autres fiches se déplacent](docs/assets/brand/identity-thread.png)

**Gardez la bonne fiche en vue.** Enregistrez son identité visible et vérifiez-la à nouveau pendant les clics réels.

[Animation](#cas-courant--ne-pas-fermer-le-mauvais-ticket) · [Aperçu local](docs/BINDING-PREVIEW.md) · [Résultats et limites](benchmarks/BINDING-V9-RESULTS.md)

> **Développement privé — 2026-10-23.** La distribution publique de la version 0.4 est suspendue. Les téléchargements ci-dessous nécessitent un accès au dépôt. Aucun avantage concurrentiel de bout en bout n'est encore démontré ; les [décisions de recherche](docs/DIRECTION.md) conservent les résultats négatifs et les critères de poursuite. Le dépôt ne redeviendra pas public sans une nouvelle autorisation explicite de son propriétaire.

Le dernier aperçu local, **0.5.0.dev9**, vérifie si un clic atteint toujours la fiche voulue après une modification de la liste. Sélectionnez une cible avec Option/Alt-clic, enregistrez-la, puis vérifiez son identité pendant l'interaction réelle. L'installation sans compilation et la démonstration dans le navigateur ont été vérifiées dans un dossier neuf. Les scénarios fixes et tous les boutons de sept sites de test montrent des différences limitées à certains mécanismes ; ils ne démontrent pas que DeltaDOM peut remplacer Browser Use en général. [Guide de l'aperçu](docs/BINDING-PREVIEW.md) · [API et limites](docs/ACTION-BINDING.md). Le code et les visuels sont dans le dépôt privé ; l'aperçu précompilé **n'a pas été ajouté à GitHub Releases**. Les anciens téléchargements 0.4 ne contiennent pas ces fonctions.

Un prototype antérieur cherche à éviter les doubles envois après une déconnexion, en isolant par objet les écritures dont l'issue reste inconnue et en limitant la réémission des requêtes. Les tests de panne du navigateur montrent un bénéfice limité pour la reprise ; les doublons non détectés et les répétitions légitimes bloquées à tort sont également conservés. Ce n'est pas encore une protection générale et elle n'est pas incluse dans le paquet 0.4. [Utilisation](docs/RECOVERY-V7-V8.md) · [Comparaisons fixes et contre-exemples](benchmarks/RECOVERY-V7-V8-RESULTS.md).

**Voyez ce qui a changé, étape par étape.**

[Télécharger l'ancien aperçu](https://github.com/Eman0n911/deltadom/releases/tag/v0.4.0) · [Installation](START_HERE.md) · [Mesures](benchmarks/RECORDING-RESULTS.md) · [SDK Python](docs/SDK.md)

DeltaDOM enregistre aussi ce que le navigateur observe, compare les changements entre étapes et restaure les observations précédentes hors ligne. Il permet d'inspecter une automatisation, d'analyser un mauvais clic ou de conserver les changements d'une page dynamique.

**La version 0.4 est expérimentale.** L'installation sans compilation a été vérifiée sur Mac Apple Silicon. La démonstration ne demande ni clé API, ni compte de modèle, ni expérience en programmation. Beaucoup de guides liés et certains messages de la CLI sont actuellement en chinois. Les légendes de l'animation commune sont en anglais.

## Nouveau prototype : voir les clics d'abord

### Cas courant : ne pas fermer le mauvais ticket

Une file de tickets se rafraîchit en permanence. Vous sélectionnez un ticket : s'il change de place, l'action suit la même fiche. Si son identité change pendant l'interaction, le clic est suspendu pour permettre une vérification.

![Animation conceptuelle : suivre le ticket bleu après un réordonnancement, puis suspendre le clic lorsqu'il devient un autre ticket orange](docs/assets/brand/identity-motion.gif)

*L'illustration et l'animation expliquent le mécanisme. Ce ne sont ni des enregistrements d'exécution, ni des garanties d'efficacité.*
[Image fixe](docs/assets/brand/identity-motion-still.png) · [Démonstration dans un vrai navigateur et limites](docs/TICKET-QUEUE-STORY.md)

### Ouvrir l'aperçu local

Décompressez le fichier fourni localement **DeltaDOM-0.5.0.dev9-macosx_11_0_arm64.zip**, puis double-cliquez sur **Start DeltaDOM.command**. Il installe les binaires précompilés et ouvre une démonstration dans un vrai navigateur, sans compte de modèle. Ce ZIP n'est pas sur GitHub Releases ; l'ancien téléchargement ci-dessous ne contient pas le nouveau prototype.

Dans le dossier du nouvel aperçu, enregistrez votre propre cible. Remplacez `https://example.com` par l'adresse de la page à utiliser :

```sh
python3 run.py bind https://example.com --output action.json
python3 run.py bound-click action.json
```

La première commande permet de sélectionner une cible en maintenant Option/Alt pendant le clic. La seconde envoie un seul clic réel vers la fiche correspondant à l'identité enregistrée, puis laisse le navigateur ouvert pour inspection. Un changement d'identité détecté arrête l'action. Il n'y a pas de nouvelle tentative automatique, et un clic n'est pas considéré comme une confirmation de réussite de l'opération métier. [Instructions détaillées](docs/BINDING-PREVIEW.md).

Pour les réordonnancements ordinaires, V9 obtient le même résultat que la référence simple et robuste de vérification du contexte, sur 281 boutons. Onze scénarios d'interaction fixes ont été testés séparément avec des gestionnaires ordinaires et avec des gestionnaires exigeant des événements d'entrée de confiance. Les clics natifs de Browser Use et les vérifications manuelles juste avant le clic ont chacun produit des effets incorrects dans 6 scénarios par type de gestionnaire ; V9 ramène ce nombre à 2. Ce n'est pas un taux de réussite de tâches de bout en bout. [Protocole, références fortes, tous les contre-exemples et résultats](benchmarks/BINDING-V9-RESULTS.md).

## Ancienne version 0.4 : enregistrer les observations

1. [Téléchargez et décompressez l'aperçu pour Mac](https://github.com/Eman0n911/deltadom/releases/download/v0.4.0/DeltaDOM-0.4.0-macosx_11_0_arm64.zip). Python 3.12 ou plus récent (ou uv) et Google Chrome sont nécessaires.
2. Double-cliquez sur **Start DeltaDOM.command**, ou lancez `python3 install.py` dans le dossier extrait.
3. Regardez le navigateur remplir un formulaire, réordonner des éléments, sélectionner un produit et recharger la page. Le terminal doit afficher **Verified 8/8**.

Rust, Node.js et un compilateur ne sont pas nécessaires. La première installation télécharge des dépendances ; la démonstration ne visite que sa page locale incluse. Consultez le [guide d'installation](START_HERE.md) en cas de difficulté. Ce n'est pas une application de bureau autonome ; elle n'est ni signée ni notarisée.

```text
STEP                   FRAME   NODES  FULL BYTES  SENT BYTES  CHECK
initial                full      304      32,556       7,203  OK
unchanged              delta     304      32,556          76  OK
fill                   delta     304      32,560         117  OK
reorder                delta     304      32,576         638  OK
same_url_reload        full      304      32,556       7,203  OK
```

Cet extrait provient d'une véritable démonstration du moteur de capture 0.3. La version 0.4 conserve cet encodage et ajoute des fichiers d'enregistrement vérifiables. [Sortie historique complète](artifacts/preview-demo-0.3.txt). Il s'agit de volumes en octets dans un exemple local, pas de coûts d'utilisation d'un modèle.

## Examiner les changements

Après la démonstration, exécutez ces commandes dans le dossier extrait :

```sh
# Vérifier l'intégrité de l'enregistrement sans ouvrir de navigateur
python3 run.py replay deltadom-output/demo.ddt

# Comparer les observations avant et après la saisie du formulaire
python3 run.py diff deltadom-output/demo.ddt --before 2 --after 3

# Restaurer l'étape 3 en JSON lisible
python3 run.py replay deltadom-output/demo.ddt --step 3 --output step-3.json
```

Pour enregistrer votre propre page :

```sh
python3 run.py record https://example.com --count 30 --output example.ddt
```

Interagissez avec la fenêtre de navigateur séparée ; DeltaDOM enregistre une fois par seconde. Les enregistrements restent locaux et peuvent contenir des données privées issues des pages ou des formulaires : vérifiez-les avant de les partager. Le profil connecté de votre navigateur habituel n'est pas chargé. Les fichiers d'enregistrement et d'export existants ne sont pas écrasés. [Enregistrement, reprise après interruption et intégration](docs/RECORDING.md).

## Ajouter l'enregistrement à un agent existant

Dans un environnement Python où le wheel est installé, conservez votre modèle Browser Use et votre logique d'action :

```python
from deltadom import BrowserUseRecorder

with BrowserUseRecorder("agent.ddt") as recorder:
    await agent.run(on_step_end=recorder.on_step_end)
```

Ce rappel a été vérifié avec Browser Use **0.13.11**. Il enregistre la dernière entrée du modèle, sa sortie et les résultats d'action à la fin de chaque étape. Il ne modifie pas l'entrée du modèle et ne capture pas toutes les requêtes au fournisseur ni toutes les nouvelles tentatives. Il utilise un champ privé de MessageManager : il faut donc le revérifier après une mise à jour. [Périmètre de l'interface](docs/RECORDING.md#接入已有-browser-use-智能体).

Avec Playwright, `DeltaBrowser` prend aussi en charge les différences entre nœuds sémantiques, les actions par identifiant stable et la lecture de champs d'API explicitement autorisés. [SDK](docs/SDK.md) · [Exemple](examples/observe.py).

## Résultats mesurés

| Comparaison | Résultat | Périmètre |
|---|---|---|
| Sauvegarde de la même sortie Browser Use, image par image | **48,7 % à 59,1 % d'octets en moins** | Par rapport à une compression zlib indépendante avec des contrôles d'intégrité équivalents, sur des enregistrements de pages existants |
| Restauration du contenu original | **450/450 identiques octet par octet** | Trois sources d'observation, 150 instantanés chacune |
| Archive gzip de toute la session | **gzip est plus petit** | Préférez gzip si vous voulez seulement une sauvegarde après la tâche |
| Coût du modèle et réussite de bout en bout | **Aucune amélioration démontrée** | Le rappel d'enregistrement ne modifie pas l'entrée du modèle |

[Protocole, résultats complets et résultats négatifs](benchmarks/RECORDING-RESULTS.md). Dans des comparaisons antérieures de la couche d'observation sur des pages publiques, les différences natives d'agent-browser étaient plus courtes et la capture DOM native de Browser Use était plus rapide. Une économie de stockage ne démontre pas une supériorité sur les agents de navigation.

## Quel outil choisir ?

- Pour une IA qui accomplit des tâches Web de façon autonome : [Browser Use](https://github.com/browser-use/browser-use).
- Pour piloter un navigateur depuis le terminal : [agent-browser](https://github.com/vercel-labs/agent-browser).
- Pour l'enregistrement incrémental de pages, les comparaisons champ par champ, la validation et la restauration d'observations : essayez DeltaDOM avec vos outils actuels.

Le format utilise zlib standard avec l'image précédente comme dictionnaire. Son intérêt réside dans la combinaison de la validation, de l'enregistrement incrémental et de la reprise. Ce n'est pas un nouvel algorithme de compression, et nous ne prétendons pas que les autres outils n'ont pas de fonctions de relecture. Ces projets ne sont pas affiliés.

## Périmètre et limites

- V9 enregistre et rejoue un clic à la fois ; il ne planifie pas des tâches complètes. Il prend actuellement en charge les contrôles HTML courants au niveau principal de la page et exige exactement l'URL enregistrée. Certains changements échappent à la détection. Il ne peut ni annuler les effets de gestionnaires déjà exécutés, ni confirmer le résultat métier côté serveur.
- La restauration exacte porte sur les nœuds sémantiques capturés ou le texte natif, pas sur le HTML complet, une vidéo ou l'état du navigateur. La capture Playwright exclut le contenu interne des iframes, les racines shadow fermées et les pixels des canvas.
- L'observation comprend par défaut une attente de stabilisation de 60 ms. Elle peut signaler une instabilité, sans garantir que la page ne changera pas ensuite.
- Une étape enregistrée est limitée à 16 MiB ; les tableaux de messages contenant l'historique et des captures d'écran en base64 peuvent naturellement dépasser cette limite. `BrowserUseRecorder` enregistre alors un marqueur d'omission avec l'étape, le nombre de messages et la taille en octets, sans interrompre l'agent. La relecture indique `omitted_snapshots` ; le contenu omis ne peut pas être restauré. Les autres erreurs d'écriture ou de sérialisation sont toujours propagées. Un enregistrement endommagé échoue à la validation. `replay --recover` restaure la partie initiale vérifiée d'un enregistrement interrompu et la marque comme incomplète. Les empreintes d'intégrité n'authentifient pas l'origine.
- L'aperçu Mac arm64 a été installé et vérifié localement. Les vérifications du code ou de la compilation sur d'autres plateformes ne valent pas vérification d'installation de leurs paquets téléchargeables.

## Développement et contributions

[Vérifications des versions précédentes](docs/VALIDATION-0.4.md) · [Développement et tests](CONTRIBUTING.md) · [Conception](docs/DESIGN.md) · [Décisions de recherche](docs/DIRECTION.md) · [Historique des changements](CHANGELOG.md)

MIT · [Mentions relatives aux tiers](THIRD_PARTY_NOTICES.md). Les pages permettant de reproduire un problème et les signalements de bogues sont les bienvenus ; n'incluez pas de vrais mots de passe, cookies ou historiques personnels de navigation.
