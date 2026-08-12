// 사내 점심 취향 12개 문항 설문 UI 로직
let currentUserId = "";
let selectedDepartment = "";
const selectedAllergies = new Set();
const selectedDislikes = new Set();
const categoryScores = {};
const tastePreferences = {};
const selectedStyles = new Set();
let selectedBudget = "";
let selectedPriorities = [];
let dataConsent = true;

// 카테고리 목록 및 취향 항목 초기화
const categoriesList = [
    "한식", "중식", "일식", "양식", "분식", "치킨", "피자", "햄버거",
    "쌀국수", "아시안", "샐러드", "고기", "해산물", "국밥", "찌개", "면류"
];

const tasteItemsList = [
    "매운 음식", "기름진 음식", "담백한 음식", "국물 있는 음식", "고기 위주",
    "채소 위주", "탄수화물 위주", "건강식", "든든한 식사", "가벼운 식사"
];

function selectSingleChip(groupClass, el, val, callback) {
    document.querySelectorAll(groupClass).forEach(c => c.classList.remove("selected"));
    el.classList.add("selected");
    callback(val);
}

function toggleMultiChip(el, targetSet) {
    el.classList.toggle("selected");
    const text = el.innerText.trim();
    if (el.classList.contains("selected")) {
        targetSet.add(text);
    } else {
        targetSet.delete(text);
    }
}

function setScore(type, name, score, btnEl) {
    if (type === 'cat') {
        categoryScores[name] = score;
    } else {
        tastePreferences[name] = score;
    }
    const parent = btnEl.parentElement;
    parent.querySelectorAll(".score-btn").forEach(b => b.classList.remove("active"));
    btnEl.classList.add("active");
}

function togglePriorityChip(el, name) {
    const idx = selectedPriorities.indexOf(name);
    if (idx > -1) {
        selectedPriorities.splice(idx, 1);
        el.classList.remove("selected");
        el.innerText = name;
    } else {
        if (selectedPriorities.length >= 3) {
            alert("중요 순위는 최대 3개까지 선택할 수 있습니다.");
            return;
        }
        selectedPriorities.push(name);
        el.classList.add("selected");
        el.innerText = `${selectedPriorities.length}순위: ${name}`;
    }
}

function setConsent(val, el) {
    dataConsent = val;
    document.querySelectorAll(".consent-chip").forEach(c => c.classList.remove("selected"));
    el.classList.add("selected");
}

async function startSurvey() {
    const inputEl = document.getElementById("user-id-input");
    const name = inputEl ? inputEl.value.trim() : "";
    if (!name) return alert("이름을 입력해주세요.");
    currentUserId = name;
    document.getElementById("display-name").innerText = currentUserId;
    document.getElementById("step-login").style.display = "none";
    document.getElementById("step-survey").style.display = "block";

    try {
        const res = await fetch(`/api/surveys/${encodeURIComponent(currentUserId)}`);
        if (res.ok) {
            const data = await res.json();
            populateFromJSON(data);
        }
    } catch (err) {
        console.log("신규 설문 시작");
    }
}

function populateFromJSON(data) {
    // 알러지 칩 동기화
    selectedAllergies.clear();
    (data.allergies || []).forEach(a => {
        selectedAllergies.add(a);
        document.querySelectorAll("#allergy-chips .chip").forEach(c => {
            if (c.innerText.trim() === a) c.classList.add("selected");
        });
    });

    // 기피 음식 칩 동기화
    selectedDislikes.clear();
    (data.dislikes || []).forEach(d => {
        selectedDislikes.add(d);
        document.querySelectorAll("#dislike-chips .chip").forEach(c => {
            if (c.innerText.trim() === d) c.classList.add("selected");
        });
    });

    // 카테고리 점수 동기화
    if (data.category_scores) {
        Object.keys(data.category_scores).forEach(cat => {
            categoryScores[cat] = data.category_scores[cat];
            const row = document.getElementById(`cat-row-${cat}`);
            if (row) {
                row.querySelectorAll(".score-btn").forEach(btn => {
                    btn.classList.toggle("active", parseInt(btn.innerText) === data.category_scores[cat]);
                });
            }
        });
    }

    // 취향 점수 동기화
    if (data.taste_preferences) {
        Object.keys(data.taste_preferences).forEach(item => {
            tastePreferences[item] = data.taste_preferences[item];
            const row = document.getElementById(`taste-row-${item}`);
            if (row) {
                row.querySelectorAll(".score-btn").forEach(btn => {
                    btn.classList.toggle("active", parseInt(btn.innerText) === data.taste_preferences[item]);
                });
            }
        });
    }

    if (data.recent_favorites) {
        const el = document.getElementById("recent-favorites");
        if (el) el.value = data.recent_favorites;
    }
    if (data.recent_fatigue) {
        const el = document.getElementById("recent-fatigue");
        if (el) el.value = data.recent_fatigue;
    }
}

async function saveSurvey() {
    if (!currentUserId) {
        const inputEl = document.getElementById("user-id-input");
        currentUserId = (inputEl && inputEl.value.trim()) || localStorage.getItem("survey_user_id") || prompt("설문자 성함을 입력해주세요 (예: 대균):", "대균");
        if (!currentUserId) {
            alert("이름을 입력해야 설문이 저장됩니다.");
            return;
        }
    }

    const customAllergies = document.getElementById("custom-allergy").value
        .split(",").map(s => s.trim()).filter(s => s.length > 0);
    const customDislikes = document.getElementById("custom-dislike").value
        .split(",").map(s => s.trim()).filter(s => s.length > 0);

    const payload = {
        user_id: currentUserId,
        department: selectedDepartment,
        allergies: Array.from(selectedAllergies).concat(customAllergies),
        dislikes: Array.from(selectedDislikes).concat(customDislikes),
        category_scores: categoryScores,
        taste_preferences: tastePreferences,
        lunch_styles: Array.from(selectedStyles),
        budget: selectedBudget,
        recent_favorites: document.getElementById("recent-favorites").value.trim(),
        recent_fatigue: document.getElementById("recent-fatigue").value.trim(),
        priority_order: selectedPriorities,
        data_collection_consent: dataConsent
    };

    const res = await fetch("/api/survey", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    });
    if (res.ok) {
        localStorage.setItem("survey_user_id", currentUserId);
        localStorage.setItem("feedback_user_id", currentUserId);
        alert(`✨ [${currentUserId}님] 12개 문항 취향 설문이 서버 DB에 완벽히 저장되었습니다!\n이제 맞춤 점심 추천 메인 화면으로 자동 이동합니다.`);
        location.href = "/";
    } else {
        alert("저장에 실패했습니다.");
    }
}

document.addEventListener("DOMContentLoaded", () => {
    const savedName = localStorage.getItem("survey_user_id");
    const inputEl = document.getElementById("user-id-input");
    if (savedName && inputEl) {
        inputEl.value = savedName;
    }
});
