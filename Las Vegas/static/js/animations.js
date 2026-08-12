// animations.js

window.sleep = function(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
};

window.animateDiceRoll = async function(container, results, color) {
    // We already do a simple CSS bounce animation in showRolledDice
    // But if we want a complex one, we can do rapid replacements
    const originalContent = [];
    
    // Rapid phase
    for (let i = 0; i < 10; i++) {
        container.innerHTML = '';
        results.forEach(() => {
            const randVal = Math.floor(Math.random() * 6) + 1;
            const tempDice = createDiceFace(randVal, color);
            tempDice.classList.add('anim-shake');
            container.appendChild(tempDice);
        });
        await sleep(100);
    }
    
    // Settle phase is handled by caller replacing HTML
};

window.animateBillDeal = async function(billEl, targetEl) {
    // For a complex fly animation, we'd need getBoundingClientRect of both
    // For now, simple CSS slideUp is applied in renderCasinos
};

window.showConfetti = function(container) {
    // Generate simple CSS confetti
    for (let i = 0; i < 50; i++) {
        const c = document.createElement('div');
        c.className = 'confetti';
        c.style.left = `${Math.random() * 100}%`;
        c.style.top = `-10px`;
        c.style.backgroundColor = ['#c58686', '#c4b56f', '#7fa88e', '#4f8cc9'][Math.floor(Math.random() * 4)];
        c.style.animationDuration = `${Math.random() * 3 + 2}s`;
        c.style.animationDelay = `${Math.random()}s`;
        container.appendChild(c);
    }
};
