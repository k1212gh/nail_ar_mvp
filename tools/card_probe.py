"""실사진에서 신용카드 검출을 눈으로 검증하는 도구 (실환경 강건성 확인용).

사용: python tools/card_probe.py <image.jpg> [out.jpg]
카드를 찾으면 4모서리+mm/px 를 그려 저장하고 콘솔에 수치를 출력한다.
카드가 손톱과 같은 평면에 있으면, 이 mm/px 로 손톱 실치수가 바로 나온다.
"""
import os
import sys

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.card_scale import detect_card, nail_mm   # noqa: E402


def main(argv) -> int:
    if len(argv) < 2:
        print("사용: python tools/card_probe.py <image> [out]")
        return 2
    img = cv2.imread(argv[1])
    if img is None:
        print("이미지를 못 읽었습니다:", argv[1])
        return 2
    card = detect_card(img)
    if not card:
        print("카드 미검출 — 조명/대비/각도를 바꿔 다시 시도하세요.")
        return 1
    mmpp = card["mm_per_px"]
    print(f"카드 검출: long={card['long_px']:.0f}px short={card['short_px']:.0f}px "
          f"aspect={card['aspect']:.3f} (규격 1.586) mm/px={mmpp:.4f} "
          f"area={card['area_frac'] * 100:.1f}%")
    # 참고: 12mm 손톱은 화면상 몇 px 인지
    print(f"  → 화면상 손톱 {12.0 / mmpp:.0f}px 이면 실측 12mm")
    c = card["corners"].astype(int)
    for i in range(4):
        cv2.line(img, tuple(c[i]), tuple(c[(i + 1) % 4]), (0, 255, 0), 2)
        cv2.circle(img, tuple(c[i]), 5, (0, 0, 255), -1)
    cv2.putText(img, f"{mmpp:.4f} mm/px", (int(c[:, 0].min()), max(14, int(c[:, 1].min()) - 8)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    out = argv[2] if len(argv) > 2 else os.path.splitext(argv[1])[0] + "_card.jpg"
    cv2.imwrite(out, img)
    print("저장:", out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
