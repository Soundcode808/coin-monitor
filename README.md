# 업비트-바이낸스 김치프리미엄 모니터링 도구

---

## 💻 처음 쓰는 분을 위한 설치 및 사용법 (Windows 기준)

### 1단계 — Python 설치

1. 브라우저에서 **python.org** 접속
2. 상단 Downloads 클릭 → 최신 버전 다운로드
3. 설치 시작할 때 **"Add Python to PATH"** 체크박스 반드시 체크 후 Install Now 클릭

---

### 2단계 — 폴더 준비

받은 `코인 모니터링` 폴더를 본인 컴퓨터 아무 곳에나 저장합니다.
예: `C:\Users\홍길동\Documents\코인 모니터링`

---

### 3단계 — 패키지 설치 (처음 한 번만)

1. 키보드에서 **윈도우 키 + R** 누르기
2. `cmd` 입력 후 확인
3. 아래 명령어 입력 (폴더 경로는 본인 것으로 변경)

```
cd "C:\Users\홍길동\Documents\코인 모니터링"
pip install -r requirements.txt
```

---

### 4단계 — 실행

```
python main.py
```

화면에 로그가 뜨면 정상 작동 중입니다.
업비트-바이낸스 괴리율이 기준치를 넘으면 **텔레그램 그룹으로 자동 알림**이 갑니다.

---

### 5단계 — 종료

명령 프롬프트 창에서 **Ctrl + C** 를 누릅니다.

---

### 주의사항

- 프로그램이 실행 중인 동안만 알림이 옵니다. **컴퓨터를 끄면 알림도 멈춥니다.**
- 처음 실행 시 첫 번째 조회는 알림 없이 기준값만 잡습니다 (정상입니다).
- 바이낸스가 한국 IP를 차단할 경우 VPN이 필요합니다.

---

> **주의: 한국 IP에서는 바이낸스 API가 차단될 수 있습니다.**
> 바이낸스가 451 오류를 반환하면 VPN을 켜거나 해외 클라우드 서버에서 실행해야 합니다.
> 국내 IP 차단은 바이낸스 정책 문제이며 이 도구의 버그가 아닙니다.

---

## 1. 이 도구가 뭐 하는지

업비트(원화)와 바이낸스(달러) 사이의 코인 가격 차이(김치프리미엄/역프리미엄)를 30초마다 자동으로 확인합니다.
지정한 기준(기본 3%)을 넘으면 텔레그램으로 알림을 보내고, 결과를 엑셀에서 열 수 있는 CSV 파일에 기록합니다.
설정 파일(config.yaml) 하나만 수정하면 임계값, 코인 목록, 알림 간격을 자유롭게 바꿀 수 있습니다.

---

## 2. 준비물

- **Python 3.10 이상** — [python.org](https://www.python.org/downloads/) 에서 다운로드
- **pip** — Python 설치 시 함께 설치됨
- **텔레그램 봇 토큰** — 아래 3번 참고
- **(선택) 환율 API 키** — 없어도 무료 폴백 자동 사용

---

## 3. 설치

명령 프롬프트(cmd)를 열고 아래 명령을 실행합니다.

```
cd "<설치한 폴더 경로>"
pip install -r requirements.txt
```

> `<설치한 폴더 경로>` 부분을 본인이 파일을 저장한 실제 경로로 바꿔주세요.
> 예: `cd "C:\Users\홍길동\Documents\코인 모니터링"`
> 폴더 이름에 한글과 띄어쓰기가 있으므로 반드시 큰따옴표로 감싸야 합니다.

---

## 4. 텔레그램 봇 만들기

1. 텔레그램 앱에서 **@BotFather** 를 검색해서 대화를 시작합니다.
2. `/newbot` 을 입력합니다.
3. 봇 이름을 입력합니다. (예: `김프모니터`)
4. 봇 아이디(username)를 입력합니다. 영문+숫자, 끝에 `bot` 필수. (예: `kimchi_monitor_bot`)
5. BotFather가 **토큰**을 알려줍니다. 예시: `1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ`
6. 이 토큰을 복사해서 config.yaml의 `bot_token` 항목에 붙여넣습니다.

---

## 5. Chat ID 확인

1. 방금 만든 봇에게 텔레그램에서 아무 메시지나 보냅니다. (예: `안녕`)
2. 브라우저에서 아래 주소를 엽니다. `<토큰>` 부분을 실제 토큰으로 교체합니다.
   ```
   https://api.telegram.org/bot<토큰>/getUpdates
   ```
3. 화면에 JSON 텍스트가 나타납니다. `"chat"` 항목 안의 `"id"` 숫자를 찾습니다.
   ```json
   "chat": { "id": 123456789, "type": "private" ... }
   ```
4. 그 숫자를 복사해서 config.yaml의 `chat_id` 항목에 붙여넣습니다.

---

## 6. 환율 API 키 발급 (선택)

키가 없어도 `open.er-api.com` 무료 서비스가 자동으로 사용됩니다. 더 정확한 환율이 필요하면 아래에서 발급받을 수 있습니다.

- **한국수출입은행**: [https://www.koreaexim.go.kr/site/program/financial/exchangeJSON](https://www.koreaexim.go.kr/site/program/financial/exchangeJSON)
- **한국은행 ECOS**: [https://ecos.bok.or.kr/api/#/](https://ecos.bok.or.kr/api/#/)

발급받은 키는 config.yaml의 `fx.exim_api_key` 또는 `fx.ecos_api_key` 항목에 입력합니다.

---

## 7. config.yaml 작성

명령 프롬프트에서 아래 명령으로 예시 파일을 복사합니다.

```
cd "<설치한 폴더 경로>"
copy config.example.yaml config.yaml
```

> `<설치한 폴더 경로>` 부분을 본인의 실제 경로로 바꿔주세요.

메모장으로 `config.yaml` 을 열고 아래 두 항목을 필수로 수정합니다.

```yaml
telegram:
  bot_token: "실제_봇_토큰_입력"
  chat_id: "실제_챗ID_숫자_입력"
```

---

## 8. 실행

```
cd "<설치한 폴더 경로>"
python main.py
```

> `<설치한 폴더 경로>` 부분을 본인의 실제 경로로 바꿔주세요.

실행하면 로그가 화면에 출력됩니다. 공통 코인 추출 → 가격 조회 → 알림 순서로 동작합니다.

---

## 9. 종료

실행 중인 명령 프롬프트 창에서 **Ctrl + C** 를 누릅니다.

---

## 10. 임계값·코인 변경

`config.yaml` 을 메모장으로 열어서 수정한 뒤 프로그램을 재시작합니다.

```yaml
threshold_percent: 3.0      # 이 숫자를 바꾸면 알림 기준 변경
check_interval_sec: 30      # 조회 간격 (초)
watch_coins: ["BTC", "ETH"] # 특정 코인만 보고 싶을 때 — 비워두면 전체
```

---

## 11. 자주 발생하는 오류

| 오류 | 원인 | 해결 방법 |
|------|------|-----------|
| `바이낸스 API 451 오류` | 한국 IP 차단 | VPN 연결 또는 해외 서버에서 실행 |
| `텔레그램 전송 실패 401` | 봇 토큰이 잘못됨 | config.yaml의 `bot_token` 재확인 |
| `텔레그램 전송 실패 400` | chat_id가 잘못됨 | config.yaml의 `chat_id` 재확인 |
| `config.yaml 파일이 없습니다` | 설정 파일 미생성 | `copy config.example.yaml config.yaml` 실행 후 토큰 입력 |
| `모든 환율 소스 조회 실패` | 인터넷 연결 문제 | 인터넷 연결 확인 |

---

## 12. CSV 파일 확인

알림이 발생할 때마다 같은 폴더의 `alerts.csv` 에 자동 기록됩니다.
파일을 더블클릭하면 엑셀에서 한글이 깨지지 않고 열립니다.

| 시각 | 코인 | 업비트가 | 바이낸스환산가 | 괴리율 | 방향 |
|------|------|---------|--------------|--------|------|
| 2026-04-20 10:30:00 | BTC | 135,000,000 | 130,000,000 | +3.85% | 김치프리미엄 |

---

## 13. Oracle Cloud 서버 운영 가이드

### 1) 서버 접속 (맥북 터미널에서)
```
ssh -i ~/Downloads/ssh-key-2026-04-20.key ubuntu@192.18.137.207
```

### 2) 프로그램 실행
서버 접속 후:
```
cd ~/coin-monitor && python3 main.py
```

### 3) 백그라운드로 실행 (터미널 꺼도 계속 돌아감)
```
cd ~/coin-monitor && nohup python3 main.py > log.txt 2>&1 &
```

### 4) 백그라운드 실행 중지
```
pkill -f "python3 main.py"
```

### 5) 실시간 로그 보기
```
tail -f ~/coin-monitor/log.txt
```

---

## 14. 코드 수정 후 서버 반영하는 법

**순서:**

1. Claude Code에서 코드 수정

2. 맥북 터미널에서 GitHub에 올리기:
```
cd "/Users/vesper/Documents/코인 모니터링" && git add . && git commit -m "수정내용" && git push
```

3. 서버 터미널에서 받아오고 재실행:
```
pkill -f "python3 main.py"
cd ~/coin-monitor && git pull
nohup python3 main.py > log.txt 2>&1 &
```

---

## 15. config.yaml 서버에서 수정하는 법

텔레그램 명령어(!거래소, !기준 등)로 수정하거나, 직접 서버에서 편집:
```
nano ~/coin-monitor/config.yaml
```
저장: `Ctrl+O` → 엔터 → `Ctrl+X`

---

## 파일 구조

```
코인 모니터링/
  main.py                # 메인 실행 파일
  notifier.py            # 텔레그램·사운드 알림
  fx.py                  # 환율 조회
  exchanges.py           # 업비트·바이낸스 가격 조회
  config.example.yaml    # 설정 예시 (이것을 복사해서 config.yaml 만들기)
  config.yaml            # 실제 설정 파일 (본인만 보관, 절대 공유 금지)
  requirements.txt       # 필요한 패키지 목록
  alerts.csv             # 알림 기록 (자동 생성)
```
