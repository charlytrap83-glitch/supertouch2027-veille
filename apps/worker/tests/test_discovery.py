"""Le worker découvre bien le workflow de veille muette (aucun envoi de mail)."""

import mistralai.workflows as workflows

from worker.workflows.veille_imap import VeilleInput


def test_st2027_veille_imap_discovered() -> None:
    classes = workflows.discover_all_workflows_in_package("worker.workflows")
    names = [workflows.get_workflow_definition(c).name for c in classes]
    assert "st2027_veille_imap" in names


def test_veille_input_defaults() -> None:
    v = VeilleInput()
    assert v.mode == "once"
    assert v.last_uid == 0
    assert v.interval_minutes == 12


def test_veille_input_muette_sans_destinataire() -> None:
    # Règle du 17 nov. 2026 : plus aucun champ de destinataire, aucun envoi de mail.
    champs = set(VeilleInput.model_fields.keys())
    assert "alert_dest" not in champs
    assert all("dest" not in c for c in champs)
