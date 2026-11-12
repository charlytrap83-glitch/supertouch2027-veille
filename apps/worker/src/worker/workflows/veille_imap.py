"""Veille IMAP SuperTouch2027 (12 nov. 2026).

Relais de veille de la boîte supertouch@touchfrance.fr (OVH) : les sessions
planifiées Vibe ne peuvent pas faire de relevé IMAP direct, ce workflow relevé
la boîte en lecture seule et prévient Charles par email ([ST2027] à
charlytrapani@hotmail.fr, boîte lue aussi par les 96 veilles via Outlook).

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
import smtplib
from datetime import timedelta
from email.message import EmailMessage
from email.utils import parsedate_to_datetime

import mistralai.workflows as workflows
from pydantic import BaseModel

IMAP_HOST = "ssl0.ovh.net"
IMAP_PORT = 993
SMTP_HOST = "ssl0.ovh.net"
SMTP_PORT = 587
COMPTE = "supertouch@touchfrance.fr"


class VeilleInput(BaseModel):
    """État plat du workflow : mêmes champs pour le premier run et les continuations."""

    mode: str = "once"  # "once" | "daemon"
    last_uid: int = 0  # plus haut UID IMAP déjà traité (0 = initialisation)
    interval_minutes: int = 15  # cadence du mode daemon
    alert_dest: str = "charlytrapani@hotmail.fr"


def _mdp() -> str | None:
    return os.environ.get("ST2027_OVH_PASSWORD") or None


def _entete(msg: EmailMessage, nom: str) -> str:
    v = msg.get(nom, "")
    return " ".join(str(v).split()) if v else ""


def _apercu(msg: EmailMessage, limite: int = 220) -> str:
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
            # Initialisation : borne l'état au plus haut UID existant, sans alerter
            # sur les 48 messages d'historique déjà traités par la veille Vibe.
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
        return {"erreur": f"IMAP : {type(e).__name__} : {e}"[:300], "new_last_uid": last_uid, "messages": [], "total": None, "initialise": False}
    finally:
        try:
            m.logout()
        except Exception:
            pass


@workflows.activity(start_to_close_timeout=timedelta(minutes=2))
async def envoi_alerte(dest: str, sujet: str, corps: str) -> dict:
    """Envoi du mail d'alerte via le SMTP OVH de la boîte supertouch."""
    mdp = _mdp()
    if not mdp:
        return {"envoye": False, "erreur": "ST2027_OVH_PASSWORD absent"}
    try:
        msg = EmailMessage()
        msg["From"] = f"SuperTouch2027 <{COMPTE}>"
        msg["To"] = dest
        msg["Subject"] = sujet
        msg.set_content(corps, charset="utf-8")
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
            s.starttls()
            s.login(COMPTE, mdp)
            s.send_message(msg)
        return {"envoye": True, "erreur": None}
    except Exception as e:
        return {"envoye": False, "erreur": f"SMTP : {type(e).__name__} : {e}"[:300]}


def corps_alerte(releve: dict) -> str:
    """Corps de l'email d'alerte, un point par nouveau mail."""
    lignes = [
        "Relevé automatique de la boîte supertouch@touchfrance.fr (lecture seule).",
        "",
        f"{len(releve.get('messages') or [])} nouveau(x) mail(s) :",
        "",
    ]
    for i, m in enumerate(releve.get("messages") or [], 1):
        lignes.append(f"{i}. De : {m.get('de', '(expéditeur inconnu)')}")
        if m.get("sujet"):
            lignes.append(f"   Objet : {m['sujet']}")
        if m.get("date"):
            lignes.append(f"   Date : {m['date']}")
        if m.get("apercu"):
            lignes.append(f"   Aperçu : {m['apercu']}")
        lignes.append("")
    lignes.append("Les veilles Vibe reprennent ces mails pour le CRM. Aucune action immédiate nécessaire sauf urgence signalée.")
    return "\n".join(lignes)


@workflows.workflow.define(name="st2027_veille_imap")
class VeilleImap:
    @workflows.workflow.entrypoint
    async def run(self, data: VeilleInput) -> dict:
        releve = await releve_imap(data.last_uid)
        last_uid = releve["new_last_uid"] or data.last_uid
        erreur = releve.get("erreur")
        alerte = False
        erreur_envoi = None
        if not erreur and releve.get("messages"):
            sujet = f"[ST2027] Veille : {len(releve['messages'])} nouveau(x) mail(s) sur supertouch@touchfrance.fr"
            r = await envoi_alerte(data.alert_dest, sujet, corps_alerte(releve))
            alerte = bool(r.get("envoye"))
            erreur_envoi = r.get("erreur")
        if data.mode == "daemon":
            await workflows.workflow.sleep(timedelta(minutes=data.interval_minutes))
            workflows.workflow.continue_as_new(
                VeilleInput(mode="daemon", last_uid=last_uid, interval_minutes=data.interval_minutes, alert_dest=data.alert_dest)
            )
        return {
            "mode": data.mode,
            "nouveaux": len(releve.get("messages") or []),
            "last_uid": last_uid,
            "total_inbox": releve.get("total"),
            "initialise": releve.get("initialise"),
            "alerte_envoyee": alerte,
            "erreur": erreur,
            "erreur_envoi": erreur_envoi,
        }
