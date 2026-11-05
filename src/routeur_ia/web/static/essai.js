// Commandes de la page en mode démonstration : demande d'essai et panne simulée.
"use strict";

const CLE_RESULTAT = "routeur-ia.dernier-essai";

async function envoyer(chemin, corps) {
  const reponse = await fetch(chemin, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(corps),
  });
  return { statut: reponse.status, donnees: await reponse.json() };
}

function resumer({ statut, donnees }) {
  if (statut !== 200) {
    return `Échec (${statut}) : ${donnees.erreur}`;
  }
  const bascule = donnees.bascule ? ", après bascule" : "";
  return `Modèle ${donnees.modele} (niveau ${donnees.decision.niveau})${bascule}, coût ${donnees.cout_usd} $.`;
}

document.querySelector("#essai").addEventListener("submit", async (evenement) => {
  evenement.preventDefault();
  const champs = new FormData(evenement.target);
  const retour = await envoyer("/v1/demandes", {
    tache: champs.get("tache"),
    message: champs.get("message"),
  });
  sessionStorage.setItem(CLE_RESULTAT, resumer(retour));
  location.reload();
});

for (const bouton of document.querySelectorAll(".bouton-panne")) {
  bouton.addEventListener("click", async () => {
    await envoyer("/demo/panne", {
      fournisseur: bouton.dataset.fournisseur,
      active: bouton.dataset.active === "true",
    });
    location.reload();
  });
}

const resultat = sessionStorage.getItem(CLE_RESULTAT);
if (resultat) {
  document.querySelector("#essai-resultat").textContent = resultat;
  sessionStorage.removeItem(CLE_RESULTAT);
}
