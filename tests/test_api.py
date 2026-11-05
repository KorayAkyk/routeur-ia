"""API JSON, à travers le client de test Flask."""

from collections.abc import Mapping
from pathlib import Path

import pytest
from flask.testing import FlaskClient

from routeur_ia.composition import Application
from routeur_ia.domaine import ErreurRequete, ErreurTransitoire, Fournisseur
from routeur_ia.web import creer_app
from tests.aides import creer_application, creer_config, faux_fournisseurs

CORPS = {"tache": "resume", "message": "Résume ce texte.", "max_jetons": 100}


@pytest.fixture
def application(tmp_path: Path) -> Application:
    return creer_application(tmp_path / "j.sqlite")


@pytest.fixture
def client(application: Application) -> FlaskClient:
    return creer_app(application).test_client()


def faux(application: Application, nom: str) -> object:
    return application.fournisseurs[nom]


def test_sante(client: FlaskClient) -> None:
    assert client.get("/sante").json == {"statut": "ok", "mode": "faux"}


def test_demande_reussie(client: FlaskClient) -> None:
    reponse = client.post("/v1/demandes", json=CORPS)
    assert reponse.status_code == 200
    donnees = reponse.json
    assert donnees is not None
    assert donnees["modele"] == "a-std"
    assert donnees["fournisseur"] == "anthropic"
    assert donnees["bascule"] is False
    assert donnees["arret"] == "fin"
    assert donnees["decision"]["niveau"] == "standard"
    assert donnees["decision"]["candidats"] == ["a-std", "g-std"]
    assert donnees["decision"]["etapes"][0]["regle"] == "tache"
    assert donnees["essais"] == [{"modele": "a-std", "essai": 1, "statut": "ok", "code": None}]
    assert float(donnees["cout_usd"]) > 0


def test_valeurs_par_defaut(client: FlaskClient) -> None:
    donnees = client.post("/v1/demandes", json={"message": "x" * 600}).json
    assert donnees is not None
    assert donnees["decision"]["niveau"] == "standard"


def test_bascule_visible_dans_la_reponse(tmp_path: Path) -> None:
    fournisseurs = faux_fournisseurs()
    fournisseurs["anthropic"].programmer(*(ErreurTransitoire("http_529") for _ in range(3)))
    application = creer_application(tmp_path / "j.sqlite", fournisseurs=fournisseurs)
    donnees = creer_app(application).test_client().post("/v1/demandes", json=CORPS).json
    assert donnees is not None
    assert donnees["modele"] == "g-std"
    assert donnees["bascule"] is True
    assert [essai["code"] for essai in donnees["essais"]] == ["http_529"] * 3 + [None]


@pytest.mark.parametrize(
    "corps",
    [
        {},
        {"message": ""},
        {"message": 12},
        {"message": "x", "max_jetons": 0},
        {"message": "x", "max_jetons": 16001},
        {"message": "x", "champ_inconnu": 1},
        ["pas", "un", "objet"],
    ],
)
def test_corps_invalides(client: FlaskClient, corps: object) -> None:
    reponse = client.post("/v1/demandes", json=corps)
    assert reponse.status_code == 400
    assert reponse.json is not None
    assert reponse.json["erreur"] == "corps_invalide"


def test_l_erreur_de_validation_ne_renvoie_pas_la_saisie(client: FlaskClient) -> None:
    reponse = client.post("/v1/demandes", json={"message": 12, "tache": ["SECRET"]})
    assert b"SECRET" not in reponse.data


def test_json_mal_forme(client: FlaskClient) -> None:
    reponse = client.post("/v1/demandes", data="{", content_type="application/json")
    assert reponse.status_code == 400


def test_type_de_contenu_refuse(client: FlaskClient) -> None:
    """Exiger du JSON bloque aussi les formulaires envoyés depuis un autre site."""
    assert client.post("/v1/demandes", data={"message": "x"}).status_code == 415


def test_corps_trop_gros(client: FlaskClient) -> None:
    corps = '{"message": "' + "x" * (1024 * 1024 + 1) + '"}'
    reponse = client.post("/v1/demandes", data=corps, content_type="application/json")
    assert reponse.status_code == 413


def test_tache_inconnue(client: FlaskClient) -> None:
    reponse = client.post("/v1/demandes", json={"message": "x", "tache": "astrologie"})
    assert reponse.status_code == 400
    assert reponse.json == {"erreur": "tache_inconnue", "tache": "astrologie"}


def test_budget_epuise(tmp_path: Path) -> None:
    config = creer_config(budget={"plafond_mensuel_usd": "0"})
    application = creer_application(tmp_path / "j.sqlite", config)
    reponse = creer_app(application).test_client().post("/v1/demandes", json=CORPS)
    assert reponse.status_code == 402
    assert reponse.json == {"erreur": "budget_epuise"}


def test_tous_les_fournisseurs_en_echec(tmp_path: Path) -> None:
    fournisseurs = faux_fournisseurs()
    for fournisseur in fournisseurs.values():
        fournisseur.simuler_panne()
    application = creer_application(tmp_path / "j.sqlite", fournisseurs=fournisseurs)
    reponse = creer_app(application).test_client().post("/v1/demandes", json=CORPS)
    assert reponse.status_code == 503
    assert reponse.json is not None
    assert reponse.json["erreur"] == "aucun_fournisseur"
    assert len(reponse.json["essais"]) == 6


def test_demande_refusee_par_le_fournisseur(tmp_path: Path) -> None:
    fournisseurs = faux_fournisseurs()
    fournisseurs["anthropic"].programmer(ErreurRequete("http_400"))
    application = creer_application(tmp_path / "j.sqlite", fournisseurs=fournisseurs)
    reponse = creer_app(application).test_client().post("/v1/demandes", json=CORPS)
    assert reponse.status_code == 422
    assert reponse.json is not None
    assert reponse.json["code"] == "http_400"


def test_simuler_ne_depense_rien_et_n_ecrit_rien(
    client: FlaskClient, application: Application
) -> None:
    reponse = client.post("/v1/routage/simuler", json={"tache": "code", "message": "x"})
    assert reponse.json is not None
    assert reponse.json["niveau"] == "expert"
    assert application.journal.derniers_appels() == []
    faux_anthropic = application.fournisseurs["anthropic"]
    assert faux_anthropic.requetes == []  # type: ignore[attr-defined]


def test_agent(client: FlaskClient) -> None:
    donnees = client.post("/v1/agent", json={"objectif": "Combien font 6 * 7 ?"}).json
    assert donnees is not None
    assert donnees["arret"] == "termine"
    assert "42" in donnees["texte"]
    assert donnees["etapes"][0]["appels"][0]["outil"] == "calculer"
    assert donnees["etapes"][0]["resultats"][0]["contenu"] == "42"


def test_couts(client: FlaskClient) -> None:
    client.post("/v1/demandes", json=CORPS)
    donnees = client.get("/v1/couts?jours=7").json
    assert donnees is not None
    assert donnees["depuis"] == "2026-03-09"
    assert donnees["lignes"][0]["modele"] == "a-std"
    assert donnees["lignes"][0]["jour"] == "2026-03-15"
    assert donnees["lignes"][0]["appels"] == 1


@pytest.mark.parametrize("jours", ["0", "-1", "367"])
def test_couts_periode_invalide(client: FlaskClient, jours: str) -> None:
    assert client.get(f"/v1/couts?jours={jours}").status_code == 400


def test_budget(client: FlaskClient) -> None:
    assert client.get("/v1/budget").json == {
        "plafond_usd": "10.000000",
        "depense_usd": "0.000000",
        "restant_usd": "10.000000",
        "part_restante": 1.0,
    }


def test_panne_simulee_puis_retablie(client: FlaskClient, application: Application) -> None:
    corps = {"fournisseur": "anthropic", "active": True}
    assert client.post("/demo/panne", json=corps).status_code == 200
    donnees = client.post("/v1/demandes", json=CORPS).json
    assert donnees is not None
    assert donnees["modele"] == "g-std"

    client.post("/demo/panne", json={"fournisseur": "anthropic", "active": False})
    donnees = client.post("/v1/demandes", json=CORPS).json
    assert donnees is not None
    assert donnees["modele"] == "a-std"
    assert application.sante.est_disponible("anthropic")


def test_panne_d_un_fournisseur_inconnu(client: FlaskClient) -> None:
    corps = {"fournisseur": "inconnu", "active": True}
    assert client.post("/demo/panne", json=corps).status_code == 404


def test_la_panne_simulee_n_existe_pas_en_mode_reel(tmp_path: Path) -> None:
    fournisseurs: Mapping[str, Fournisseur] = faux_fournisseurs()
    application = creer_application(tmp_path / "j.sqlite", fournisseurs=fournisseurs, mode="reel")
    client = creer_app(application).test_client()
    corps = {"fournisseur": "anthropic", "active": True}
    assert client.post("/demo/panne", json=corps).status_code == 404


def test_route_inconnue_en_json(client: FlaskClient) -> None:
    reponse = client.get("/nulle-part")
    assert reponse.status_code == 404
    assert reponse.json == {"erreur": "not_found"}
