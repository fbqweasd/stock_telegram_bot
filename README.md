# 📈 Stock Alert Telegram Bot

**텔레그램 주식 알림 봇**

> 특정 주식의 티커를 구독하면 주기적으로 해당 주식의 기술적 지표를 분석하여 
> **20선 이탈, 볼린저 밴드 돌파, RSI 과매수/과매도** 등의 이벤트 발생 시 텔레그램으로 알림을 보내줍니다.
> 또한 모든 지표를 통합하여 **매수/매도 목표가와 추천 등급**을 예측해 줍니다.

---

## ✨ 주요 기능

| 기능 | 설명 |
|------|------|
| **📊 기술적 알림** | 20일선 이탈/회복, 볼린저 밴드 상/하단 돌파, RSI 과매수/과매도 |
| **🎯 가격 예측** | 모든 보조지표를 통합한 매수/매도 목표가 및 추천 등급 |
| **⏰ 자동 스캔** | 일정 주기(기본 1시간)마다 모든 구독 종목 스캔 |
| **📋 구독 관리** | `/add`, `/del`, `/list` 명령어로 손쉬운 구독 관리 |
| **🌅 장 시작 전 알림** | 매일 8:30 시장 인덱스 현황 자동 전송 |
| **🚨 극단 조건 알림** | VIX 급등, 공포탐욕지수 극단값, 지수 급등락 시 자동 알림 |
| **📈 시장 인덱스 조회** | `/indices` 명령어로 실시간 시장 현황 확인 |

---

## 🚀 빠른 시작

### 1. 텔레그램 봇 생성

1. 텔레그램에서 [@BotFather](https://t.me/BotFather) 에게 `/newbot` 명령어로 새 봇을 생성합니다.
2. 발급받은 **토큰**을 복사해 둡니다.

### 2. 환경 변수 설정

```bash
# .env.example 파일을 .env로 복사 후 토큰 입력
cp .env.example .env
# 또는 수동으로 .env 파일 생성 후 아래 내용 입력
```

**.env 파일 내용:**
```ini
TELEGRAM_BOT_TOKEN=여기에_봇_토큰_입력
CHECK_INTERVAL=3600
DB_PATH=data/stock_bot.db
```

### 3. 실행

```bash
# 직접 실행 (Python 3.8+)
python main.py

# 또는 Docker로 실행
docker build -t stock-alert-bot .
docker run -d \
  --name stock-bot \
  -e TELEGRAM_BOT_TOKEN="여기에_봇_토큰_입력" \
  -v stock-bot-data:/app/data \
  stock-alert-bot
```

---

## 🐳 Docker 배포

### Docker Hub / GitHub Container Registry

```bash
# 이미지 빌드
docker build -t stock-alert-bot .

# 실행 (데이터 볼륨 마운트)
docker run -d \
  --name stock-bot \
  --restart unless-stopped \
  -e TELEGRAM_BOT_TOKEN="your_token_here" \
  -e CHECK_INTERVAL=3600 \
  -v stock-bot-data:/app/data \
  stock-alert-bot

# 로그 확인
docker logs -f stock-bot
```

### docker-compose.yml (선택)

```yaml
version: '3.8'
services:
  stock-bot:
    build: .
    container_name: stock-alert-bot
    restart: unless-stopped
    environment:
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - CHECK_INTERVAL=${CHECK_INTERVAL:-3600}
      - DB_PATH=/app/data/stock_bot.db
    volumes:
      - stock-bot-data:/app/data

volumes:
  stock-bot-data:
```

---

## 📖 명령어 사용법

| 명령어 | 설명 | 예시 |
|--------|------|------|
| `/start` | 환영 메시지 | `/start` |
| `/help` | 명령어 목록 확인 | `/help` |
| `/add [티커]` | 관심 주식 등록 | `/add AAPL`, `/add 005930.KS` |
| `/del [티커]` | 관심 주식 삭제 | `/del AAPL` |
| `/list` | 구독 목록 조회 | `/list` |
| `/predict [티커]` | 기술적 분석 & 예측 리포트 | `/predict TSLA` |
| `/indices` | 시장 인덱스 현황 조회 | `/indices`, `/지수`, `/시장` |

> **티커 표기법:**
> - 미국 주식: `AAPL`, `TSLA`, `MSFT`
> - 한국 코스피: `005930.KS` (삼성전자), `000660.KS` (SK하이닉스)
> - 한국 코스닥: `247540.KQ` (에코프로비엠)

---

## 🛠️ 기술 스택

| 항목 | 내용 |
|------|------|
| **언어** | Python 3.11+ (표준 라이브러리만 사용) |
| **API** | Telegram Bot API (urllib), Yahoo Finance (urllib), Alternative.me (공포탐욕지수) |
| **데이터베이스** | SQLite3 (내장) |
| **지표 계산** | SMA, 볼린저 밴드, RSI (Wilder Smoothing), 지지/저항 |
| **예측 모델** | 규칙 기반 휴리스틱 (Rule-based) |
| **배포** | Docker (python:3.11-slim) |

---

## 📂 프로젝트 구조

```
stock_bot/
├── config.py          # 환경 변수 로드 및 설정
├── database.py        # SQLite 데이터베이스 (구독/시그널 관리)
├── indicators.py      # 기술적 지표 계산 (SMA, BB, RSI, 지지/저항)
├── main.py            # 진입점 (초기화 및 실행)
├── market_indices.py  # 시장 인덱스 데이터 수집 (공포탐욕지수, VIX, 지수, 환율, 국채)
├── predictor.py       # 매수/매도 가격 예측
├── scheduler.py       # 백그라운드 알림 스케줄러
├── stock_api.py       # Yahoo Finance API 연동
├── telegram_bot.py    # 텔레그램 봇 (명령어 처리/메시지 전송)
├── Dockerfile         # 도커 이미지 빌드
├── requirements.txt   # 의존성 명세 (표준 라이브러리만)
├── .env.example       # 환경 변수 템플릿
├── .gitignore         # Git 제외 파일
└── README.md          # 프로젝트 설명 (이 파일)
```

---

## 🔔 자동 알림 기능

### 🌅 장 시작 전 시장 현황 (매일 8:30)
- 매일 한국 시간 8:30에 시장 인덱스 현황을 자동으로 전송합니다
- 공포탐욕지수, VIX, 주요 지수(S&P500, NASDAQ, DOW), 환율, 국채수익률 포함

### 🚨 극단적 시장 조건 알림
다음 조건 감지 시 자동으로 알림을 보내드립니다:
- **VIX 25 이상**: 변동성 확대 구간
- **VIX 30 이상**: 시장 공포 극대화
- **공포탐욕지수 25 이하**: 공포 구간
- **공포탐욕지수 75 이상**: 탐욕 구간
- **주요 지수 2% 이상 급등락**
- **원/달러 환율 2% 이상 급변동**

---

## ⚠️ 주의사항

- 본 봇은 **기술적 보조지표**만을 기반으로 한 휴리스틱 예측을 제공합니다.
- **투자 권유가 아니며**, 실제 매매 결정은 본인의 판단에 따라 신중히 하시기 바랍니다.
- Yahoo Finance API는 요청 제한이 있을 수 있습니다.
- 봇이 정상 작동하려면 텔레그램 API 서버와의 연결이 가능해야 합니다.

---

## 📄 라이선스

MIT License