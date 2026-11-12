"""Le worker découvre bien le workflow de veille, et le corps d'alerte est stable."""

import mistralai.workflows as workflows

from worker.workflows.veille_imap import VeilleInput, corps_alerte


def test_st2027_veille_imap_discovered() -> None:
    classes = workflows.discover_all_workflows_in_package("worker.workflows")
    names = [workflows.get_workflow_definition(c).name for c in classes]
    assert "st2027_veille_imap" in names


def test_veille_input_defaults() -> None:
    v = VeilleInput()
    assert v.mode == "once"
    assert v.last_uid == 0
    assert v.interval_minutes == 15
    assert v.alert_dest == "charlytrapani@hotmail.fr"


def test_corps_alerte_liste_les_mails() -> None:
    releve = {
        "messages": [
            {"uid": 51, "de": "club@example.fr", "sujet": "Candidature J1", "date": "12 nov. 2026 09h12", "apercu": "Bonjour, nous souhaitons…"},
        ],
        "total": 49,
    }
    corps = corps_alerte(releve)
    assert "club@example.fr" in corps
    assert "Candidature J1" in corps
    assert "1 nouveau(x) mail(s)" in corps
    assert "supertouch@touchfrance.fr" in corps
