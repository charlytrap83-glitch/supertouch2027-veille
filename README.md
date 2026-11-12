# supertouch2027-veille

Workflow Mistral de relais de veille pour le Championnat Super Touch 2027 (projet de Charles Trapani, commission SuperTouch / LNT, Touch France).

## Pourquoi

Les sessions de veille planifiées Vibe ne peuvent pas faire de relevé IMAP direct (verdict établi le 12 nov. 2026 : ni node, ni python3, ni curl/openssl dans leur environnement). Ce workflow relève la boîte `supertouch@touchfrance.fr` (OVH) en lecture seule et prévient par email, lu à la fois par Charles et par les 96 veilles via le connecteur Outlook.

## Fonctionnement

- **Workflow** : `st2027_veille_imap` (module `apps/worker/src/worker/workflows/veille_imap.py`).
- **Mode `once`** (validation) : `{"mode":"once"}` fait un seul relevé, résultat visible dans les événements d'exécution. Premier passage avec `last_uid=0` : initialisation silencieuse (borne l'état au plus haut UID, aucune alerte sur l'historique déjà traité).
- **Mode `daemon`** : `{"mode":"daemon"}` boucle durable : relevé, alerte si nouveaux mails, `workflow.sleep(15 min)`, `continue_as_new` avec le dernier UID traité. État plat `VeilleInput`.
- **Lecture seule stricte** : IMAP `EXAMINE` (`select` readonly) + `BODY.PEEK` : aucun mail marqué lu, rien déplacé ni supprimé.
- **Alertes** : `[ST2027] Veille : N nouveau(x) mail(s)...` à `charlytrapani@hotmail.fr`, via SMTP OVH (ssl0.ovh.net:587 STARTTLS), depuis `supertouch@touchfrance.fr`.

## Secret requis

`ST2027_OVH_PASSWORD` (secret d'espace de travail Mistral, console.mistral.ai/secrets) : mot de passe OVH de `supertouch@touchfrance.fr`. Il est lié au déploiement via le binding `secrets` (même nom de variable d'environnement). Aucune valeur en dur dans le code, les tests ou les images.

## Déploiement (déjà lu : get_workflow_builder_instructions)

1. Dépôt GitHub privé `supertouch2027-veille` (compte charlytrap83-glitch), code poussé sur `main` via le connecteur github_app.
2. `deploy_workflow_deployment` : nom stable `st2027-veille-imap`, `github_url` = URL du dépôt, `revision` = SHA poussé, `build_directory` = `.`, `dockerfile_path` = `deploy/docker/Dockerfile.worker`, `secrets` = `[{secret_name: "st2027_ovh_password", env_var_name: "ST2027_OVH_PASSWORD"}]` (le nom du secret Studio est en minuscules).
3. `wait_workflow_deployment_ready` jusqu'à `ready=true` sur le SHA.
4. Validation : exécution `{"mode":"once"}` (doit renvoyer `initialise: true`, `nouveaux: 0`), puis démarrage `{"mode":"daemon"}`.

## Règles du projet

- Jamais d'email aux clubs sans instruction explicite de Charles : ce workflow n'envoie QUE l'alerte [ST2027] à la boîte personnelle de Charles.
- La boîte `supertouch@touchfrance.fr` reste en lecture seule pour la veille ; les réponses aux clubs suivent le protocole habituel (accusés de candidature, validation de Charles).
