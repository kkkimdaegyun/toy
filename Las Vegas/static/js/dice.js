// dice.js

window.createDiceFace = function(value, colorStr) {
    // Determine exact hex color
    let hexColor = colorStr;
    if (COLOR_HEX[colorStr]) {
        hexColor = COLOR_HEX[colorStr];
    }

    const svgNS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("viewBox", "0 0 100 100");
    svg.setAttribute("class", "dice-svg");
    
    // Background rect
    const rect = document.createElementNS(svgNS, "rect");
    rect.setAttribute("x", "5");
    rect.setAttribute("y", "5");
    rect.setAttribute("width", "90");
    rect.setAttribute("height", "90");
    rect.setAttribute("rx", "20");
    rect.setAttribute("ry", "20");
    rect.setAttribute("fill", hexColor);
    rect.setAttribute("class", "dice-face");
    
    // Add inner shadow/highlight effect
    const inset = document.createElementNS(svgNS, "rect");
    inset.setAttribute("x", "10");
    inset.setAttribute("y", "10");
    inset.setAttribute("width", "80");
    inset.setAttribute("height", "80");
    inset.setAttribute("rx", "15");
    inset.setAttribute("ry", "15");
    inset.setAttribute("fill", "url(#diceGrad)");
    inset.setAttribute("opacity", "0.3");

    // Defs for gradient
    const defs = document.createElementNS(svgNS, "defs");
    const grad = document.createElementNS(svgNS, "linearGradient");
    grad.setAttribute("id", "diceGrad");
    grad.setAttribute("x1", "0%"); grad.setAttribute("y1", "0%");
    grad.setAttribute("x2", "100%"); grad.setAttribute("y2", "100%");
    
    const stop1 = document.createElementNS(svgNS, "stop");
    stop1.setAttribute("offset", "0%"); stop1.setAttribute("stop-color", "white"); stop1.setAttribute("stop-opacity", "0.5");
    const stop2 = document.createElementNS(svgNS, "stop");
    stop2.setAttribute("offset", "100%"); stop2.setAttribute("stop-color", "black"); stop2.setAttribute("stop-opacity", "0.5");
    
    grad.appendChild(stop1);
    grad.appendChild(stop2);
    defs.appendChild(grad);
    
    svg.appendChild(defs);
    svg.appendChild(rect);
    svg.appendChild(inset);

    // Pip layout coordinates
    const pips = {
        1: [[50, 50]],
        2: [[25, 25], [75, 75]],
        3: [[25, 25], [50, 50], [75, 75]],
        4: [[25, 25], [25, 75], [75, 25], [75, 75]],
        5: [[25, 25], [25, 75], [50, 50], [75, 25], [75, 75]],
        6: [[25, 25], [25, 50], [25, 75], [75, 25], [75, 50], [75, 75]]
    };

    const pipColor = "white"; // Always white with drop shadow for dark contrast
    
    if (pips[value]) {
        pips[value].forEach(coords => {
            const circle = document.createElementNS(svgNS, "circle");
            circle.setAttribute("cx", coords[0]);
            circle.setAttribute("cy", coords[1]);
            circle.setAttribute("r", "10");
            circle.setAttribute("fill", pipColor);
            
            // Add slight shadow to pip
            circle.setAttribute("filter", "drop-shadow(1px 1px 2px rgba(0,0,0,0.5))");
            
            svg.appendChild(circle);
        });
    }

    return svg;
};
