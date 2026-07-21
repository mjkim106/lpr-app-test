"""사용자 정의 액션 (대시보드 '액션 관리'에서 추가/수정/삭제됨).

각 액션은 함수:  def <action>(ctx, target):
  ctx = KeywordRunner 인스턴스. 아래 헬퍼를 사용할 수 있음:
    ctx._adb("shell","input","keyevent","4")     # adb 명령
    ctx._tap_frac(534, 2172)                       # 1080x2400 기준 좌표 탭
    ctx._src()                                     # 현재 화면 page_source(str)
    ctx.tap_text("시작하기") / ctx.assert_visible("텍스트") 등 기존 액션도 호출 가능
    target = 엑셀 target 칸 값(문자열)

함수는 반드시 마커 주석 사이에 둔다(대시보드가 이 마커로 추가/삭제):
  # === action: 이름 ===
  def 이름(ctx, target): ...
  # === end: 이름 ===
"""
import time  # noqa: F401  (사용자 액션에서 사용)

