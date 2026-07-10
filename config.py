"""중앙 설정값. 명령행 인자로 대부분 덮어쓸 수 있다 (main.py 참고).

[모듈형 설계 핵심]
- 카메라/영상 입력은 'source' 문자열 하나로만 결정된다.
- 폰(DroidCam), 웹캠, 파일, 그리고 향후 '스마트글래스(XREAL Eye 등)'까지
  같은 인터페이스(VideoSource)를 쓰므로, source 값만 바꾸면 파이프라인은 그대로 동작한다.
  예) source="0"            → PC 웹캠
      source="http://..."   → 폰 DroidCam/IP Webcam
      source="clip.mp4"     → 파일
      source="glasses"      → 스마트글래스(어댑터에서 프레임 공급)
"""
from dataclasses import dataclass, field


@dataclass
class HandConfig:
    model_path: str = "models/hand_landmarker.task"  # 없으면 자동 다운로드 시도
    max_hands: int = 2
    min_detection_confidence: float = 0.5
    min_presence_confidence: float = 0.5
    min_tracking_confidence: float = 0.5
    # 손톱 ROI: TIP~DIP 거리에 곱해 ROI 한 변 크기를 정한다.
    roi_scale: float = 1.6
    roi_min_px: int = 28
    # 핀홀 거리모델용 초점거리 = focal_ratio * 이미지폭(px). 카메라 HFOV에 따라(≈0.8~1.0).
    focal_ratio: float = 0.86


@dataclass
class SegConfig:
    # "grabcut" = 데이터 없이 즉시 동작(기본), "color" = 색상 임계(빠름), "external" = SAM/YOLO 후킹
    method: str = "grabcut"
    grabcut_iters: int = 2        # 반복 줄여 가속(3→2, 품질 차이 작음)
    # 속도: grabcut을 이 크기로 축소한 ROI에서 수행 후 마스크를 원배율로 복원(품질 손실 미미, 대폭 가속)
    grabcut_max_side: int = 112
    # 색상 기반(보조)용 HSV 범위 — 매니큐어/네일 색에 맞게 조정
    color_lower: tuple = (0, 30, 60)
    color_upper: tuple = (179, 255, 255)
    min_mask_area: int = 60
    # YOLO 손톱 세그(--seg yolo): 실제 손톱 인식
    nail_model: str = ""          # 모델 경로(.pt). 비우면 external 콜백 직접 주입
    yolo_conf: float = 0.30       # 낮을수록 더 많이 검출(오검출↑)
    yolo_imgsz: int = 640         # 클수록 작은/먼 손톱 검출↑ (4070이면 640도 실시간)


@dataclass
class GeomConfig:
    grid_rows: int = 4          # 가로 격자선 개수
    grid_cols: int = 3          # 세로 격자선 개수
    french_ratio: float = 0.30  # 손톱 끝에서 french 경계 위치(0~1, 끝=0)
    attach_points_per_edge: int = 5
    # 작업 기준 중심 산출 방식 (특허 청구항 2: 기하학적 중심/시각적 중심).
    #   "obb"=주축 방향 외접박스 중심(기본, 엄지 등 비대칭/부분 손톱 쏠림 보정)
    #   "ellipse"=손톱 외곽 타원 피팅 중심  /  "centroid"=면적 무게중심(구버전)
    center_mode: str = "obb"


@dataclass
class DesignConfig:
    """손톱에 입힐 디자인 이미지(별 등) 정합 설정 (특허 청구항 8/9)."""
    image_path: str = ""        # 입힐 PNG(RGBA). 비우면 디자인 오버레이 끔
    scale: float = 0.85         # 손톱 대비 크기(0~1, 1=손톱 외접박스)
    alpha: float = 1.0          # 전체 불투명도(0~1)
    clip_to_mask: bool = True   # 손톱 밖으로 안 넘치게 마스크로 자름
    feather: int = 3            # 가장자리 부드럽게(px)
    along: float = 0.0          # 중심에서 팁(+)/뿌리(-) 이동 비율(-1~1)
    curve: float = 0.0          # 곡면 곡률 반각(rad, 0=평면) → curv_half_angle (청구항 10/11)
    # --- A3 워핑 엔진 (DESIGN_WARP) ---
    fit_mode: str = "stretch"   # 별/T-0=stretch(현동작), 신규 디자인=contain/cover(비율보존)
    warp_tier: str = "auto"     # auto|plane|tilt|mesh|mesh_shaded (폴백 사다리)
    mesh_grid: tuple = (10, 8)  # mesh tier 격자 (ny, nx)
    feather_uv: float = 0.0     # >0이면 UV공간 페더(곡률 무관 균일). 0이면 레거시 px 페더


@dataclass
class TrackConfig:
    redetect_every: int = 6     # N 프레임마다 전체 재검출
    klt_win: int = 21
    klt_levels: int = 3
    kalman_process_noise: float = 1e-2
    kalman_measure_noise: float = 1e-1


@dataclass
class SourceConfig:
    """입력 소스 어댑터 설정. 카메라가 폰이든 글래스든 여기만 바뀐다."""
    # 파일 경로 | 웹캠 정수문자열("0") | 폰 스트림 URL | "glasses"
    source: str = "0"
    width: int = 1280           # 요청 해상도(지원 시)
    height: int = 720
    target_fps: int = 30
    flip_horizontal: bool = False
    # 스마트글래스 어댑터 전용(선택). source=="glasses"일 때만 사용.
    glasses_backend: str = "frame_dir"   # "frame_dir" | "url" | "custom"
    glasses_uri: str = ""                 # 글래스 SDK가 내보내는 프레임 폴더/스트림 URL
    # 카메라 보정값(있으면 정합 정확도↑). 글래스/폰 공통 인터페이스.
    camera_matrix: tuple = ()             # (fx, fy, cx, cy) 또는 비움
    dist_coeffs: tuple = ()


@dataclass
class AppConfig:
    src: SourceConfig = field(default_factory=SourceConfig)
    show_landmarks: bool = True
    show_roi: bool = True
    show_mask: bool = True
    show_centerline: bool = True
    show_grid: bool = True
    show_french: bool = True
    show_attach: bool = True
    show_design: bool = True    # 디자인 이미지 합성 on/off (키 'd')
    save_video: str = ""        # 비우면 저장 안 함
    bench: bool = False         # 검증 계측 표시 + 종료 요약
    bench_csv: str = ""         # 프레임별 계측 CSV 경로(비우면 저장 안 함)
    log_level: str = "INFO"     # 콘솔 로그 레벨(DEBUG/INFO/WARNING)
    log_to_file: bool = True    # logs/ 에 파일 로그 저장
    hand: HandConfig = field(default_factory=HandConfig)
    seg: SegConfig = field(default_factory=SegConfig)
    geom: GeomConfig = field(default_factory=GeomConfig)
    design: DesignConfig = field(default_factory=DesignConfig)
    track: TrackConfig = field(default_factory=TrackConfig)
