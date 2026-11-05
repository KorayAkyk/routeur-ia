"""Page de suivi des coûts."""

from datetime import timedelta

from flask import Blueprint, render_template, request

from routeur_ia.web.contexte import application_courante
from routeur_ia.web.presentation import construire_graphique, totaux_par_modele

suivi = Blueprint("suivi", __name__)

PERIODES = (7, 30, 90)
PERIODE_PAR_DEFAUT = 30


@suivi.get("/")
def page_suivi() -> str:
    application = application_courante()
    jours = request.args.get("jours", default=PERIODE_PAR_DEFAUT, type=int)
    if jours not in PERIODES:
        jours = PERIODE_PAR_DEFAUT

    aujourdhui = application.horloge().date()
    debut = aujourdhui - timedelta(days=jours - 1)
    lignes = application.journal.couts_par_jour_et_modele(debut)
    # La couleur suit le modèle, jamais son rang : on se base sur l'ordre de la configuration.
    series = {modele: rang for rang, modele in enumerate(application.config.modeles)}
    totaux = totaux_par_modele(lignes, series)
    budget = application.budget.etat()
    part_depensee = (
        min(1.0, budget.depense_nano / budget.plafond_nano) if budget.plafond_nano else 1.0
    )

    return render_template(
        "suivi.html",
        mode_faux=application.mode_faux,
        jours=jours,
        periodes=PERIODES,
        budget=budget,
        pourcentage_depense=round(part_depensee * 100),
        graphique=construire_graphique(lignes, debut, aujourdhui, series),
        legende=[(modele, series[modele]) for modele in application.config.modeles],
        lignes=list(reversed(lignes)),
        totaux=totaux,
        cout_periode=sum(t.cout_nano for t in totaux),
        appels_periode=sum(t.appels for t in totaux),
        echecs_periode=sum(t.echecs for t in totaux),
        derniers=application.journal.derniers_appels(12),
        fournisseurs=[
            {
                "nom": nom,
                "disponible": application.sante.est_disponible(nom),
                "simule_panne": getattr(fournisseur, "en_panne", False),
            }
            for nom, fournisseur in sorted(application.fournisseurs.items())
        ],
        taches=sorted(application.config.routage.niveau_par_tache),
    )
