"""Veille IMAP SuperTouch2027, version muette (17 nov. 2026).

Relais de veille de la boîte supertouch@touchfrance.fr (OVH) en lecture seule.
RÈGLE DE CHARLES DU 17 NOV. 2026 : plus aucun envoi de mail, ni vers les clubs
ni vers Charles (fin des alertes [ST2027] et des comptes rendus par mail).
Le workflow se limite donc à RELEVÉR : chaque nouveau mail est consigné dans
le résultat de l'exécution (lisible via les événements d'exécution du déploiement
Mistral), aucune écriture, aucun envoi SMTP, aucune notification.

Deux modes :
  - "once"   : un seul relevé (validation), résultat dans les événements.
  - "daemon" : boucle durable (sleep + continue_as_new), état plat porté par
               VeilleInput, dernier UID traité en champ last_uid.

Secret d'espace de travail requis : ST2027_OVH_PASSWORD (mot de passe OVH de
supertouch@touchfrance.fr), lié à la variable d'environnement du même nom au
déploiement. Aucune valeur en dur dans le code.
"""

import email
import email.policy
import imaplib
import os
from datetime import timedelta
from email.utils import parsedate_to_datetime

import mistralai.workflows as workflows
from pydantic import BaseModel

IMAP_HOST = "ssl0.ovh.net"
IMAP_PORT = 993
COMPTE = "supertouch@touchfrance.fr"


class VeilleInput(BaseModel):
    """État plat du workflow : mêmes champs pour le premier run et les continuations."""

    mode: str = "once"  # "once" | "daemon"
    last_uid: int = 0  # plus haut UID IMAP déjà traité (0 = initialisation)
    interval_minutes: int = 12  # cadence du mode daemon


def _mdp() -> str | None:
    return os.environ.get("ST2027_OVH_PASSWORD") or None


def _entete(msg: email.message.EmailMessage, nom: str) -> str:
    v = msg.get(nom, "")
    return " ".join(str(v).split()) if v else ""


def _apercu(msg: email.message.EmailMessage, limite: int = 220) -> str:
    try:
        corps = msg.get_body(preferencelist=("plain",))
        if corps is None:
            return ""
        texte = corps.get_content()
        texte = " ".join(texte.split())
        return texte[:limite] + ("…" if len(texte) > limite else "")
    except Exception:
        return ""


@workflows.activity(start_to_close_timeout=timedelta(minutes=3))
async def releve_imap(last_uid: int) -> dict:
    """Relevé de l'INBOX en lecture seule (EXAMINE, BODY.PEEK : rien n'est marqué lu)."""
    mdp = _mdp()
    if not mdp:
        return {"erreur": "ST2027_OVH_PASSWORD absent", "new_last_uid": last_uid, "messages": [], "total": None, "initialise": False}
    m = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    try:
        m.login(COMPTE, mdp)
        m.select("INBOX", readonly=True)  # EXAMINE : lecture seule stricte
        typ, data = m.uid("search", None, "ALL")
        uids = [int(u) for u in (data[0] or b"").split()] if typ == "OK" and data and data[0] else []
        total = len(uids)
        if last_uid <= 0:
            # Initialisation : borne l'état au plus haut UID existant, silencieux.
            return {"erreur": None, "new_last_uid": (max(uids) if uids else 0), "messages": [], "total": total, "initialise": True}
        nouveaux = []
        for uid in (u for u in uids if u > last_uid):
            typ, d = m.uid("fetch", str(uid), "(BODY.PEEK[])")
            brut = d[0][1] if typ == "OK" and d and isinstance(d[0], tuple) else b""
            msg = email.message_from_bytes(brut, policy=email.policy.default)
            date = _entete(msg, "Date")
            try:
                date = parsedate_to_datetime(date).strftime("%d %b %Y %Hh%M") if date else ""
            except Exception:
                pass
            nouveaux.append(
                {
                    "uid": uid,
                    "de": _entete(msg, "From"),
                    "sujet": _entete(msg, "Subject"),
                    "date": date,
                    "apercu": _apercu(msg),
                }
            )
        return {
            "erreur": None,
            "new_last_uid": (max(uids) if uids else last_uid),
            "messages": nouveaux,
            "total": total,
            "initialise": False,
        }
    except Exception as e:  # résilience du daemon : l'erreur remonte dans le résultat, pas d'arrêt
        return {"erreur": f"IMAP : {type(e).__name__} : {e}"[:400], "new_last_uid": last_uid, "messages": [], "total": None, "initialise": False}
    finally:
        try:
            m.logout()
        except Exception:
            pass


@workflows.workflow.define(name="st2027_veille_imap")
class VeilleImap:
    @workflows.workflow.entrypoint
    async def run(self, data: VeilleInput) -> dict:
        releve = await releve_imap(data.last_uid)
        last_uid = releve["new_last_uid"] or data.last_uid
        if data.mode == "daemon":
            await workflows.workflow.sleep(timedelta(minutes=data.interval_minutes))
            workflows.workflow.continue_as_new(
                VeilleInput(mode="daemon", last_uid=last_uid, interval_minutes=data.interval_minutes)
            )
        return {
            "mode": data.mode,
            "nouveaux": len(releve.get("messages") or []),
            "messages": releve.get("messages") or [],
            "last_uid": last_uid,
            "total_inbox": releve.get("total"),
            "initialise": releve.get("initialise"),
            "erreur": releve.get("erreur"),
        }
