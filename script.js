// Commentaires
function envoyerCommentaire(publicationId) {
    const input = document.getElementById(`comment-input-${publicationId}`);
    const texte = input.value.trim();
    
    if (!texte) return;
    
    fetch('/ajouter-commentaire', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({publication_id: publicationId, texte: texte})
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            alert(data.error);
        } else {
            input.value = '';
            location.reload();
        }
    });
}

// Réaction publication
function reagirPublication(publicationId, button) {
    fetch('/reagir-publication', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({publication_id: publicationId})
    })
    .then(response => response.json())
    .then(data => {
        const spanNb = button.querySelector('.nb-coeurs');
        const currentNb = parseInt(spanNb.textContent);
        
        if (data.action === 'like') {
            spanNb.textContent = currentNb + 1;
            button.classList.remove('coeur-inactive');
            button.classList.add('coeur-active');
        } else {
            spanNb.textContent = currentNb - 1;
            button.classList.remove('coeur-active');
            button.classList.add('coeur-inactive');
        }
    });
}