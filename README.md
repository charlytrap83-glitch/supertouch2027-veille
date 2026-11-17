# supertouch2027-veille

Workflow Mistral de relais de veille pour le Championnat Super Touch 2027 (projet de Charles Trapani, commission SuperTouch / LNT, Touch France).

## Pourquoi

Les sessions de veille planifiées Vibe ne peuvent pas faire de relevé IMAP direct (verdict établi le 12 nov. 2026 : ni node, ni python3, ni curl/openssl dans leur environnement). Ce workflow relève la boîte `supertouch@touchfrance.fr` (OVH) en lecture seule.

**Version muette (17 nov. 2026)** : règle de Charles, aucun envoi de mail par ce workflow, ni vers les clubs ni vers Charles. Fin des alertes `[ST2027]` et de tout compte rendu par mail. Les relevés se lisent dans les événements d'exécution du déploiement (`list_executions` puis `read_workflow_execution_events` côté assistant Vibe).

## Fonctionnement

- **Workflow** : `st2027_veille_imap` (module `apps/worker/src/worker/workflows/veille_imap.py`).
- **Mode `once`** (validation) : `{"mode":"once"}` fait un seul relevé, résultat visible dans les événements d'exécution. Premier passage avec `last_uid=0` : initialisation silencieuse (borne l'état au plus haut UID).
- **Mode `daemon`** : `{"mode":"daemon"}` boucle durable : relevé, `workflow.sleep(12 min)`, `continue_as_new` avec le dernier UID traité. État plat `VeilleInput` (`mode`, `last_uid`, `interval_minutes`).
- **Lecture seule stricte** : IMAP `EXAMINE` (`select` readonly) + `BODY.PEEK` : aucun mail marqué lu, rien déplacé ni supprimé. Aucune connexion SMTP, aucun envoi.
- **Traçabilité** : chaque exécution retourne `nouveaux`, le détail des nouveaux mails (`de`, `sujet`, `date`, `apercu`), `last_uid`, `total_inbox` et `erreur` : c'est la seule sortie de la veille.

## Secret requis

`ST2027_OVH_PASSWORD` (secret d'espace de travail Mistral, console.mistral.ai/secrets) : mot de passe OVH de `supertouch@touchfrance.fr`. Il est lié au déploiement via le binding `secrets` (même nom de variable d'environnement). Aucune valeur en dur dans le code, les tests ou les images.

## Déploiement (déjà lu : get_workflow_builder_instructions)

1. Dépôt GitHub `supertouch2027-veille` (compte charlytrap83-glitch), code poussé sur `main` (flux appareil GitHub depuis l'assistant, le connecteur github_app étant en lecture seule).
2. `deploy_workflow_deployment` : nom stable `st2027-veille-imap`, `github_url` = URL du dépôt, `revision` = SHA poussé, `build_directory` = `.`, `dockerfile_path` = `deploy/docker/Dockerfile.worker`, `secrets` = `[{secret_name: "st2027_ovh_password", env_var_name: "ST2027_OVH_PASSWORD"}]` (le nom du secret Studio est en minuscules).
3. `wait_workflow_deployment_ready` jusqu'à `ready=true` sur le SHA.
4. Validation : exécution `{"mode":"once"}` (doit renvoyer `initialise: true`, `nouveaux: 0`), puis démarrage `{"mode":"daemon"}`.

## Règles du projet

- **Règle du 17 nov. 2026** : aucun mail n'est envoyé sans accord explicite de Charles, ni vers les clubs ni vers Charles lui-même. Ce workflow n'envoie strictement rien : il relève, consigne dans ses événements, et c'est tout.
- La boîte `supertouch@touchfrance.fr` reste en lecture seule pour la veille ; les réponses aux clubs suivent le protocole habituel (accord explicite de Charles sur le mail précis avant tout envoi).
