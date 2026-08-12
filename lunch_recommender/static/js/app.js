// 점심 메뉴 추천 검색 + 피드백 별점 제출
let lastRecommendations = [];

function setQuery(text) {
    const el = document.getElementById('query-input');
    if (el) { el.value = text; doSearch(); }
}

async function doSearch() {
    const el = document.getElementById('query-input');
    if (!el) return;
    const q = el.value.trim();
    if (!q) return;

    try {
        const res = await fetch('/api/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: q })
        });
        const data = await res.json();
        lastRecommendations = data.recommendations || [];

        document.getElementById('results-section').style.display = 'block';

        // 참여자 및 컨텍스트 안내
        const participants = (data.participants || []).join(', ');
        let noteHtml = `<strong>👥 참여 멤버:</strong> ${participants}<br>`;
        if (data.context_notes && data.context_notes.length) {
            noteHtml += `<strong>🎯 AI 문맥 분석:</strong> ${data.context_notes.join(' / ')}`;
        }
        document.getElementById('info-bar').innerHTML = noteHtml;

        // 추천 결과 카드 렌더링
        const container = document.getElementById('cards-container');
        container.innerHTML = '';

        lastRecommendations.forEach((item, idx) => {
            const scoreColor = item.final_score >= 80 ? '#34d399' :
                               item.final_score >= 60 ? '#fbbf24' : '#f87171';
            const safeId = item.name.replace(/[^가-힣a-zA-Z0-9]/g, '_');

            container.innerHTML += `
                <div class="card">
                    <div class="card-left">
                        <div style="display: flex; gap: 8px; margin-bottom: 8px; flex-wrap: wrap;">
                            <span class="rank-badge">TOP ${idx + 1}</span>
                            <span class="category-badge">${item.category}</span>
                        </div>
                        <h3>${item.name}</h3>
                        ${item.address ? `<p style="color: #94a3b8; font-size: 13px; margin-bottom: 6px;">📍 ${item.address}</p>` : ''}
                        ${item.recommended_menu ? `
                        <div style="margin: 8px 0 10px 0; padding: 10px 14px; background: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.45); border-radius: 10px; color: #fcd34d; font-size: 14px; font-weight: 700; display: inline-flex; align-items: center; gap: 8px;">
                            <span>💡 추천 대표 메뉴:</span>
                            <span style="color: #fff;">${item.recommended_menu}</span>
                        </div>
                        ` : ''}
                        <p>${item.reason}</p>
                    </div>
                    <div class="card-right">
                        <div class="match-rate" style="color: ${scoreColor};">${item.final_score}%</div>
                        <div style="font-size: 11px; color: #94a3b8; font-weight: 600;">매칭률</div>
                        <a href="${item.naver_map_url}" target="_blank" class="map-btn">
                            🗺️ 네이버 지도 · 리뷰
                        </a>
                    </div>
                </div>

                <div class="feedback-bar" id="fb-${safeId}">
                    <div class="feedback-main-row">
                        <span class="feedback-label">이 추천 식당에 가셨나요?</span>
                        <div class="thumbs-group">
                            <button type="button" class="btn-thumb up active" id="thumb-up-${safeId}" onclick="toggleThumb('${safeId}', true)">👍 추천 방문함</button>
                            <button type="button" class="btn-thumb down" id="thumb-down-${safeId}" onclick="toggleThumb('${safeId}', false)">👎 다른 곳 방문 (우)</button>
                        </div>
                        <div class="star-rating" id="stars-${safeId}">
                            ${[1,2,3,4,5].map(s => `<span class="star" data-score="${s}" onclick="selectStar('${safeId}', ${s})">★</span>`).join('')}
                        </div>
                        <button class="feedback-submit" onclick="submitFeedback('${item.name}', '${safeId}')">평가 및 DB 누적 저장</button>
                        <span class="feedback-done" id="done-${safeId}"></span>
                    </div>

                    <!-- 👎 눌렀을 때 열리는 RLHF 대안 식당 검색 패널 -->
                    <div class="rlhf-panel" id="rlhf-${safeId}">
                        <div class="rlhf-header">🔄 AI 추천 대신 실제 가신 식당명을 검색하거나 입력해주세요 (RLHF 대안 학습 DB 누적)</div>
                        <div class="rlhf-search-row">
                            <input type="text" id="rlhf-input-${safeId}" class="rlhf-input"
                                   placeholder="예: 성수 소바, 김치찌개 맛집..."
                                   onkeydown="if(event.key==='Enter') searchAltRestaurant('${safeId}')">
                            <button type="button" class="rlhf-search-btn" onclick="searchAltRestaurant('${safeId}')">식당 검색</button>
                        </div>
                        <div class="rlhf-results-list" id="rlhf-results-${safeId}"></div>
                        <div id="rlhf-selected-${safeId}" style="font-size: 13px; color: #34d399; font-weight: 700;"></div>
                    </div>
                </div>
            `;
        });

    } catch (err) {
        alert('추천 검색 중 오류가 발생했습니다.');
        console.error(err);
    }
}

// 별점 및 RLHF 선택 상태 관리
const selectedRatings = {};
const selectedVisitStatus = {};
const selectedAltRestaurant = {};

function toggleThumb(safeId, isVisited) {
    selectedVisitStatus[safeId] = isVisited;
    const upBtn = document.getElementById(`thumb-up-${safeId}`);
    const downBtn = document.getElementById(`thumb-down-${safeId}`);
    const rlhfPanel = document.getElementById(`rlhf-${safeId}`);

    if (isVisited) {
        upBtn?.classList.add('active');
        downBtn?.classList.remove('active');
        rlhfPanel?.classList.remove('open');
    } else {
        upBtn?.classList.remove('active');
        downBtn?.classList.add('active');
        rlhfPanel?.classList.add('open');
    }
}

async function searchAltRestaurant(safeId) {
    const inputEl = document.getElementById(`rlhf-input-${safeId}`);
    const q = inputEl ? inputEl.value.trim() : "";
    if (!q) return alert("검색할 식당명이나 키워드를 입력해주세요.");

    const listEl = document.getElementById(`rlhf-results-${safeId}`);
    if (listEl) listEl.innerHTML = `<div style="color:#94a3b8;font-size:12px;">검색 중...</div>`;

    try {
        const res = await fetch(`/api/restaurants/search?query=${encodeURIComponent(q)}`);
        const data = await res.json();
        const restaurants = data.restaurants || [];

        if (restaurants.length === 0) {
            listEl.innerHTML = `<div style="color:#f87171;font-size:12px;">검색 결과가 없습니다. 직접 입력한 이름으로 저장 가능합니다.</div>`;
            return;
        }

        listEl.innerHTML = restaurants.map(r => `
            <div class="rlhf-item">
                <div>
                    <div class="rlhf-item-title">${r.title} <span style="font-size:11px;color:#a5b4fc;">[${r.category}]</span></div>
                    <div class="rlhf-item-addr">📍 ${r.address || '상암동 인근'}</div>
                </div>
                <div class="rlhf-item-actions">
                    <a href="${r.naver_map_url}" target="_blank" style="font-size:12px;color:#a5b4fc;text-decoration:none;">🗺️ 지도</a>
                    <button type="button" class="btn-select-alt" onclick="selectAltRest('${safeId}', '${r.title}', '${r.category}')">이 식당 방문 선택</button>
                </div>
            </div>
        `).join('');
    } catch (err) {
        listEl.innerHTML = `<div style="color:#f87171;font-size:12px;">검색 중 오류 발생</div>`;
    }
}

function selectAltRest(safeId, title, category) {
    selectedAltRestaurant[safeId] = { name: title, category: category };
    const selEl = document.getElementById(`rlhf-selected-${safeId}`);
    if (selEl) selEl.innerText = `✅ 실제 방문 선택 완료: ${title} (${category})`;
}

function selectStar(safeId, score) {
    selectedRatings[safeId] = score;
    const container = document.getElementById(`stars-${safeId}`);
    if (!container) return;
    container.querySelectorAll('.star').forEach(s => {
        const v = parseInt(s.dataset.score);
        s.classList.toggle('active', v <= score);
    });
}

// 피드백 및 DB 누적 저장
async function submitFeedback(restaurantName, safeId) {
    const rating = selectedRatings[safeId];
    if (!rating) return alert('만족도 별점(1~5)을 선택해주세요.');

    const visited = selectedVisitStatus[safeId] !== undefined ? selectedVisitStatus[safeId] : true;

    let actualRestName = "";
    let actualCategory = "한식";
    if (!visited) {
        const altObj = selectedAltRestaurant[safeId];
        if (altObj) {
            actualRestName = altObj.name;
            actualCategory = altObj.category;
        } else {
            const inputEl = document.getElementById(`rlhf-input-${safeId}`);
            actualRestName = inputEl ? inputEl.value.trim() : "";
            if (!actualRestName) {
                return alert("다른 곳을 방문하셨다면, 검색 후 식당을 선택하거나 이름을 입력해주세요.");
            }
        }
    }

    let userId = localStorage.getItem('feedback_user_id');
    if (!userId) {
        userId = prompt('피드백 제출자 이름을 입력해주세요 (예: 대균):');
        if (!userId) return;
        localStorage.setItem('feedback_user_id', userId);
    }

    try {
        const res = await fetch('/api/feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: userId,
                restaurant_name: restaurantName,
                rating: rating,
                visited: visited,
                actual_restaurant_name: actualRestName,
                actual_category: actualCategory
            })
        });

        if (res.ok) {
            const doneEl = document.getElementById(`done-${safeId}`);
            if (doneEl) {
                doneEl.innerText = visited 
                    ? `✅ 추천 방문 평가 ${rating}점 DB 누적 완료!` 
                    : `✅ 대안 식당(${actualRestName}) ${rating}점 RLHF 누적 학습 완료!`;
            }
            const btn = document.querySelector(`#fb-${safeId} .feedback-submit`);
            if (btn) { btn.disabled = true; btn.style.opacity = '0.4'; }
        } else {
            alert('피드백 저장에 실패했습니다.');
        }
    } catch (err) {
        alert('서버 연결 오류');
        console.error(err);
    }
}

// 상단 설문 완료자 상태 뱃지 및 취합 통계 모달
async function loadSurveyStatusBadge() {
    const badgeContainer = document.getElementById("survey-status-badge");
    if (!badgeContainer) return;

    try {
        const res = await fetch("/api/surveys/stats");
        const data = await res.json();
        const completedNames = data.names || [];
        const myName = localStorage.getItem("survey_user_id");

        if (completedNames.length > 0) {
            const listStr = completedNames.join(", ");
            badgeContainer.innerHTML = `
                <span class="survey-badge" onclick="showSurveyStatsModal()" title="클릭하여 전체 명단 및 취합 통계 보기" style="cursor: pointer; display: inline-flex; align-items: center; gap: 6px;">
                    ✅ ${listStr}님 설문 완료 (총 ${completedNames.length}명)
                    <span style="background: rgba(255,255,255,0.18); padding: 2px 8px; border-radius: 12px; font-size: 11px;">📊 명단/통계</span>
                </span>`;
        } else if (myName) {
            badgeContainer.innerHTML = `
                <span class="survey-badge" onclick="showSurveyStatsModal()" title="클릭하여 전체 명단 및 취합 통계 보기" style="cursor: pointer; display: inline-flex; align-items: center; gap: 6px;">
                    ✅ ${myName}님 설문 완료
                    <span style="background: rgba(255,255,255,0.18); padding: 2px 8px; border-radius: 12px; font-size: 11px;">📊 명단/통계</span>
                </span>`;
        } else {
            badgeContainer.innerHTML = `
                <span class="survey-badge unregistered" onclick="location.href='/survey'" title="클릭하여 첫 설문 작성하기" style="cursor: pointer;">
                    📝 아직 설문 완료자 없음 (클릭하여 첫 등록)
                </span>`;
        }
    } catch (e) {
        const myName = localStorage.getItem("survey_user_id");
        if (myName) {
            badgeContainer.innerHTML = `<span class="survey-badge">✅ ${myName}님 설문 완료</span>`;
        } else {
            badgeContainer.innerHTML = "";
        }
    }
}

async function showSurveyStatsModal() {
    try {
        const res = await fetch("/api/surveys/stats");
        const data = await res.json();

        const oldModal = document.getElementById("survey-stats-modal");
        if (oldModal) oldModal.remove();

        const namesHtml = (data.names || []).map(n => `<span style="background: rgba(52, 211, 153, 0.2); border: 1px solid #34d399; color: #34d399; padding: 4px 12px; border-radius: 16px; font-size: 13px; font-weight: 700;">👤 ${n}</span>`).join(' ');

        const topCats = Object.entries(data.stats.category_preference || {})
            .sort((a,b) => b[1] - a[1])
            .slice(0, 3)
            .map(([cat, cnt]) => `${cat}(${cnt}명)`)
            .join(', ') || "없음";

        const modalHtml = `
            <div id="survey-stats-modal" style="position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.75); z-index: 10000; display: flex; align-items: center; justify-content: center; backdrop-filter: blur(5px);">
                <div style="background: #1e293b; border: 1px solid #334155; border-radius: 16px; width: 90%; max-width: 580px; padding: 28px; color: #f8fafc; box-shadow: 0 20px 40px rgba(0,0,0,0.5);">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; border-bottom: 1px solid #334155; padding-bottom: 12px;">
                        <h3 style="margin: 0; font-size: 19px; color: #38bdf8;">📊 설문 참여 멤버 명단 & 취합 통계</h3>
                        <button onclick="document.getElementById('survey-stats-modal').remove()" style="background: none; border: none; color: #94a3b8; font-size: 22px; cursor: pointer;">✕</button>
                    </div>

                    <!-- 1. 누가누가 했는지 리스트 -->
                    <div style="margin-bottom: 20px;">
                        <div style="font-size: 13px; color: #94a3b8; margin-bottom: 8px; font-weight: 600;">👥 설문 완료 구성원 명단 (총 ${data.total_count}명)</div>
                        <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                            ${namesHtml || '<span style="color:#94a3b8;">아직 참여자 없음</span>'}
                        </div>
                    </div>

                    <!-- 2. 취합 통계 -->
                    <div style="background: rgba(255,255,255,0.03); border: 1px solid #334155; border-radius: 12px; padding: 16px; margin-bottom: 20px;">
                        <div style="font-size: 14px; font-weight: 700; color: #facc15; margin-bottom: 12px;">📈 구성원 취향 취합 통계</div>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; font-size: 13px;">
                            <div>• <strong>가장 선호 음식:</strong> ${topCats}</div>
                            <div>• <strong>평균 선호 맵기:</strong> ${data.stats.avg_spicy_level || 0}점 / 5점</div>
                            <div>• <strong>국물 선호 비율:</strong> ${data.stats.soup_preference_ratio || 0}%</div>
                            <div>• <strong>고기 선호 비율:</strong> ${data.stats.meat_preference_ratio || 0}%</div>
                        </div>
                        ${(data.stats.allergies && data.stats.allergies.length) ? `
                        <div style="margin-top: 10px; font-size: 13px; color: #f87171;">
                            • <strong>구성원 알러지·기피 음식 취합:</strong> ${data.stats.allergies.join(', ')}
                        </div>` : ''}
                    </div>

                    <!-- 3. DB 적재 위치 안내 -->
                    <div style="background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 10px; padding: 12px; font-size: 12px; color: #e0f2fe; margin-bottom: 20px;">
                        <div style="font-weight: 700; margin-bottom: 4px;">💾 DB(데이터베이스) 적재 위치 및 동기화 상태</div>
                        <div>• 저장 경로: <code>${data.storage_info ? data.storage_info.file : 'surveys_data.json'}</code> (서버 디스크 영구 적재 중)</div>
                        <div>• 상태: ${data.storage_info ? data.storage_info.status : '정상 적재 완료'}</div>
                    </div>

                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <button onclick="resetAllSurveys()" style="background: rgba(248,113,113,0.2); color: #f87171; border: 1px solid #f87171; font-weight: 700; padding: 10px 14px; border-radius: 8px; cursor: pointer;">🗑️ 설문 전체 초기화 (테스트용)</button>
                        <div style="display: flex; gap: 10px;">
                            <button onclick="location.href='/survey'" style="background: #38bdf8; color: #0f172a; font-weight: 700; border: none; padding: 10px 18px; border-radius: 8px; cursor: pointer;">📝 설문 추가/수정</button>
                            <button onclick="document.getElementById('survey-stats-modal').remove()" style="background: #334155; color: #fff; border: none; padding: 10px 18px; border-radius: 8px; cursor: pointer;">닫기</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    } catch (e) {
        alert("취합 통계를 불러오지 못했습니다.");
        console.error(e);
    }
}

async function resetAllSurveys() {
    if (!confirm("테스트용: 저장된 모든 직원 설문 데이터 DB(surveys_data.json)를 0건으로 완전히 초기화하시겠습니까?")) return;
    try {
        const res = await fetch("/api/surveys/reset", { method: "DELETE" });
        if (res.ok) {
            localStorage.removeItem("survey_user_id");
            alert("✨ 모든 설문 데이터가 초기화되었습니다.");
            location.reload();
        } else {
            alert("초기화 실패");
        }
    } catch (e) {
        alert("서버 오류로 초기화 실패");
    }
}

document.addEventListener("DOMContentLoaded", () => {
    loadSurveyStatusBadge();
    // 다른 직원이 설문을 완료했을 때 페이지 새로고침(F5) 없이도 상단 뱃지와 통계가 5초마다 실시간 자동 동기화되도록 주기적 폴링
    setInterval(loadSurveyStatusBadge, 5000);
});
