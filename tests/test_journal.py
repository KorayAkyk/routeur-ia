"""Journal SQLite : écriture, agrégats, et ce qu'il ne doit pas contenir."""

from datetime import UTC, date, datetime
from pathlib import Path

from routeur_ia.journal import EntreeJournal, Journal
from tests.aides import creer_application, demande


def entree(
    jour: int = 10,
    modele: str = "a",
    statut: str = "ok",
    cout: int = 100,
) -> EntreeJournal:
    return EntreeJournal(
        horodatage=datetime(2026, 3, jour, 9, 30, tzinfo=UTC),
        id_demande="d1",
        tache="resume",
        niveau="standard",
        fournisseur="anthropic",
        modele=modele,
        essai=1,
        bascule=False,
        statut=statut,  # type: ignore[arg-type]
        code_erreur=None,
        jetons_entree=10,
        jetons_sortie=5,
        cout_nano=cout,
        duree_ms=12,
    )


def test_depense_depuis_inclut_le_jour_donne(tmp_path: Path) -> None:
    journal = Journal(tmp_path / "j.sqlite")
    journal.ajouter(entree(jour=9, cout=1))
    journal.ajouter(entree(jour=10, cout=10))
    journal.ajouter(entree(jour=11, cout=100))
    assert journal.depense_depuis(date(2026, 3, 10)) == 110


def test_depense_d_un_journal_vide(tmp_path: Path) -> None:
    assert Journal(tmp_path / "j.sqlite").depense_depuis(date(2026, 1, 1)) == 0


def test_agregat_par_jour_et_par_modele(tmp_path: Path) -> None:
    journal = Journal(tmp_path / "j.sqlite")
    journal.ajouter(entree(jour=10, modele="a", cout=100))
    journal.ajouter(entree(jour=10, modele="a", statut="erreur", cout=0))
    journal.ajouter(entree(jour=10, modele="b", cout=7))
    journal.ajouter(entree(jour=11, modele="a", cout=5))

    lignes = journal.couts_par_jour_et_modele(date(2026, 3, 1))

    assert [(ligne.jour.day, ligne.modele, ligne.cout_nano) for ligne in lignes] == [
        (10, "a", 100),
        (10, "b", 7),
        (11, "a", 5),
    ]
    assert lignes[0].appels == 2
    assert lignes[0].echecs == 1
    assert lignes[0].jetons_entree == 20


def test_agregat_filtre_par_date(tmp_path: Path) -> None:
    journal = Journal(tmp_path / "j.sqlite")
    journal.ajouter(entree(jour=1))
    journal.ajouter(entree(jour=20))
    assert len(journal.couts_par_jour_et_modele(date(2026, 3, 15))) == 1


def test_derniers_appels_du_plus_recent_au_plus_ancien(tmp_path: Path) -> None:
    journal = Journal(tmp_path / "j.sqlite")
    for jour in (1, 2, 3):
        journal.ajouter(entree(jour=jour))
    lignes = journal.derniers_appels(limite=2)
    assert [ligne.horodatage.day for ligne in lignes] == [3, 2]
    assert lignes[0] == entree(jour=3)


def test_le_journal_survit_a_une_reouverture(tmp_path: Path) -> None:
    chemin = tmp_path / "sous" / "dossier" / "j.sqlite"
    Journal(chemin).ajouter(entree())
    assert len(Journal(chemin).derniers_appels()) == 1


def test_le_contenu_des_demandes_n_est_jamais_enregistre(tmp_path: Path) -> None:
    chemin = tmp_path / "j.sqlite"
    application = creer_application(chemin)
    application.service.executer(demande(texte="CONTENU-PRIVE-A-NE-PAS-GARDER " * 5))

    fichiers = [p for p in tmp_path.iterdir() if p.is_file()]
    assert fichiers
    for fichier in fichiers:
        assert b"CONTENU-PRIVE" not in fichier.read_bytes()
