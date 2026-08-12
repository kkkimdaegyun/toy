// cards.js

window.createCardFace = function(value, colorStr) {
    let hexColor = colorStr;
    if (COLOR_HEX[colorStr]) {
        hexColor = COLOR_HEX[colorStr];
    }
    
    const card = document.createElement('div');
    card.className = 'card-face';
    card.style.borderColor = hexColor;
    card.style.color = hexColor;
    
    // Add subtle background tint
    card.style.backgroundColor = 'rgba(255,255,255,0.9)';
    
    card.innerHTML = `
        <div class="card-value" style="font-size: 1.5rem; line-height: 1;">${value}</div>
        <div class="card-suit" style="margin-top: 5px;">🎰</div>
    `;
    
    return card;
};
