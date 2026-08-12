import warnings
warnings.filterwarnings("ignore", category=UserWarning)

import cv2
import mediapipe as mp
import pyautogui
import time

# PyAutoGUI 안전 설정 (마우스를 모서리로 가져가면 프로그램 강제 종료)
pyautogui.FAILSAFE = True

# MediaPipe Face Mesh 초기화
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    max_num_faces=2,  # 보안 기능을 위해 최대 2명까지 감지
    refine_landmarks=True, 
    min_detection_confidence=0.6,
    min_tracking_confidence=0.6
)

cap = cv2.VideoCapture(0)

# 쿨다운 설정 (초 단위)
last_alttab_time = 0
ALTTAB_COOLDOWN = 3.0

## 회원님 눈높이에 맞춘 정면 시선 기본값 (0.38)
center_baseline = 0.38
dead_zone = 0.02  # 0.36 ~ 0.40 사이는 정지(STOP)
smooth_gaze = None

print("====================================================")
print(" 🖥️ 스마트 아이 트래커 & 바탕화면 보호 모드 (실시간 고속 반응)")
print(" [보안 기능 - 바탕화면 바로보기]")
print(" - 2명 이상 감지되거나 뒤에서 누군가 보면 즉시 바탕화면 표시 (Win + D)")
print(" [스크롤 기능 - 초고속 즉각 반응 (기준값: 0.38)]")
print(" - 화면 정면(0.38 부근) 응시 시 스크롤 정지 (STOP)")
print(" - 고개/눈을 내리면 즉시 스크롤 다운 (SCROLL DOWN)")
print(" - 고개/눈을 올리면 즉시 스크롤 업 (SCROLL UP)")
print(" ----------------------------------------------------")
print(" [키보드 조작 안내]")
print(" - 'c': 현재 시선을 정면(Center)으로 1초 캘리브레이션")
print(" - 'r': 기준값 기본 설정(0.38)으로 초기화")
print(" - 'q': 프로그램 종료")
print("====================================================")

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    # 좌우 반전 및 RGB 변환
    frame = cv2.flip(frame, 1)
    h, w, _ = frame.shape
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    
    # 얼굴 랜드마크 추출
    results = face_mesh.process(rgb_frame)
    
    if results.multi_face_landmarks:
        # [기능 1] 보안 모드: 얼굴이 2개 이상 감지될 경우 즉시 바탕화면 보기 (Win + D)
        if len(results.multi_face_landmarks) >= 2:
            current_time = time.time()
            if current_time - last_alttab_time > ALTTAB_COOLDOWN:
                print("🚨 경고: 추가 인물 감지됨! 바탕화면으로 전환합니다 (Win + D)")
                pyautogui.hotkey('win', 'd')
                last_alttab_time = current_time
            
            cv2.putText(frame, "PRIVACY ALERT: Showing Desktop!", (20, 50), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
        
        # [기능 2] 편의 모드: 혼자 있을 때 고속 고개/시선 제어
        else:
            landmarks = results.multi_face_landmarks[0].landmark
            
            # 눈·코·입 주요 시각화
            nose_tip = (int(landmarks[1].x * w), int(landmarks[1].y * h))
            mouth_center = (int(landmarks[13].x * w), int(landmarks[13].y * h))
            left_eye_pos = (int(landmarks[473].x * w), int(landmarks[473].y * h))
            right_eye_pos = (int(landmarks[468].x * w), int(landmarks[468].y * h))
            
            cv2.circle(frame, nose_tip, 4, (0, 255, 255), -1)
            cv2.circle(frame, mouth_center, 4, (255, 0, 255), -1)
            cv2.circle(frame, left_eye_pos, 3, (0, 255, 0), -1)
            cv2.circle(frame, right_eye_pos, 3, (0, 255, 0), -1)

            # 왼쪽 눈 비율 계산
            left_top_y = landmarks[159].y
            left_bottom_y = landmarks[145].y
            left_iris_y = landmarks[473].y
            left_height = left_bottom_y - left_top_y
            left_ratio = (left_iris_y - left_top_y) / left_height if left_height > 0 else center_baseline
            
            # 오른쪽 눈 비율 계산
            right_top_y = landmarks[386].y
            right_bottom_y = landmarks[374].y
            right_iris_y = landmarks[468].y
            right_height = right_bottom_y - right_top_y
            right_ratio = (right_iris_y - right_top_y) / right_height if right_height > 0 else center_baseline
            
            # 양쪽 눈 평균 비율 계산
            raw_gaze = (left_ratio + right_ratio) / 2.0
            
            # 실시간 고속 반응 필터 (기존의 딜레이를 없애고 실시간 70% 즉각 반영)
            if smooth_gaze is None:
                smooth_gaze = raw_gaze
            else:
                smooth_gaze = 0.3 * smooth_gaze + 0.7 * raw_gaze
                
            down_threshold = center_baseline + dead_zone
            up_threshold = center_baseline - dead_zone
            
            status_text = "STOP (Center)"
            color = (0, 255, 0)  # 초록색: 정지
            
            # 실시간 즉각 스크롤 (속도 및 반응성 대폭 향상)
            if smooth_gaze > down_threshold:  # 고개/눈을 위로 올릴 때
                pyautogui.scroll(55)
                status_text = "SCROLL UP ^"
                color = (0, 200, 255)
            elif smooth_gaze < up_threshold:  # 고개/눈을 아래로 내릴 때
                pyautogui.scroll(-55)
                status_text = "SCROLL DOWN v"
                color = (255, 140, 0)
                
            # 화면 상단 상태 정보 출력
            cv2.putText(frame, f"State: {status_text}", (20, 45),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
            cv2.putText(frame, f"Gaze: {smooth_gaze:.3f} (Center: {center_baseline:.3f})", (20, 85),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (220, 220, 220), 2)

    # 하단 조작법 안내
    cv2.putText(frame, "[c]: Calibrate Center | [r]: Reset | [q]: Quit", (20, frame.shape[0] - 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 180, 180), 1)

    cv2.imshow('Smart Eye Tracker & Privacy Guard', frame)

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break
    elif key == ord('c') and smooth_gaze is not None:
        center_baseline = smooth_gaze
        print(f"🎯 정면 시선 캘리브레이션 완료: 기준값 {center_baseline:.3f}")
    elif key == ord('r'):
        center_baseline = 0.38
        print("🔄 기준값 초기화 완료 (0.38)")

cap.release()
cv2.destroyAllWindows()