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
| **🇺🇸 미국장 마감 요약** | 매일 미국장 종료 후 시장 흐름 요약 자동 전송 |
| **🇰🇷 한국장 마감 요약** | 매일 한국장 종료 후 코스피/코스닥 등락·환율 요약 자동 전송 |
| **📊 주간 리포트** | 매주 월요일 아침 지난주 주요지수·관심종목 주간 변동 요약 자동 전송 |
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
| `/korea` | 한국 시장(KOSPI/KOSDAQ)·환율 조회 | `/korea`, `/한국`, `/kr` |
| `/weekly` | 지난주 주요지수·관심종목 주간 요약 | `/weekly`, `/주간`, `/w` |

> **티커 표기법:**
> - 미국 주식: `AAPL`, `TSLA`, `MSFT`
> - 한국 코스피: `005930.KS` (삼성전자), `000660.KS` (SK하이닉스)
> - 한국 코스닥: `247540.KQ` (에코프로비엠)

---

## 🔬 백테스트 (예측 정확도 검증)

실제 `predict_buy_sell_prices` 로직을 그대로 사용하여 과거 데이터 기반 예측 정확도를 검증할 수 있습니다.

### 사용법

```bash
# 기본 실행 (AAPL, 5년, 5일 후 비교)
python backtest.py --ticker AAPL

# 기간/비교일/간격 설정
python backtest.py --ticker 005930.KS --years 3 --horizon 10 --step 2

# 초기 자본 설정
python backtest.py --ticker TSLA --years 5 --horizon 5 --capital 50000

# JSON 형식으로 결과 출력
python backtest.py --ticker AAPL --years 2 --json

# 결과를 JSON 파일로 저장
python backtest.py --ticker AAPL --years 2 --output results/aapl_backtest.json
```

### 주요 옵션

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--ticker, -t` | 종목 티커 (필수) | - |
| `--years, -y` | 백테스트 기간 (년) | 5 |
| `--horizon, -H` | 예측 후 며칠 뒤 가격과 비교할지 | 5 |
| `--step, -s` | 몇 일 간격으로 예측을 실행할지 | 1 |
| `--capital, -c` | 초기 자본 | 10000 |
| `--json` | JSON 형식으로 결과 출력 | - |
| `--output, -o` | 결과를 JSON 파일로 저장 | - |

### 백테스트 원리

1. **과거 데이터만 사용** (Look-ahead bias 방지): 각 시점에서 그 시점까지의 과거 데이터만으로 예측
2. **실제 예측 로직 그대로 사용**: `predict_buy_sell_prices` 함수를 직접 호출
3. **정확도 평가**: 예측 결과(매수/매도/홀드)와 이후 실제 가격 변동 비교
4. **매매 시뮬레이션**: 매수/매도 신호에 따른 실제 수익률 계산

### 출력 지표

- **예측 정확도**: 전체/추천별/방향별/신뢰도 구간별 정확도
- **매매 성과**: 총 수익률, 승률, 평균 수익/손실, Profit Factor, 최대 낙폭, 샤프 비율
- **Buy & Hold 비교**: 전략 수익률 vs 단순 보유 수익률

### 테스트 실행

```bash
# 백테스트 모듈 단위 테스트
python -m unittest tests.test_backtest -v
```

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
├── market_indices.py  # 시장 인덱스 데이터 수집 (공포탐욕지수, VIX, 지수, 환율, 국채, KOSPI/KOSDAQ)
├── predictor.py       # 매수/매도 가격 예측
├── scheduler.py       # 백그라운드 알림 스케줄러
├── stock_api.py       # Yahoo Finance API 연동
├── telegram_bot.py    # 텔레그램 봇 (명령어 처리/메시지 전송)
├── backtest.py        # 백테스트 (예측 정확도 검증)
├── Dockerfile         # 도커 이미지 빌드
├── requirements.txt   # 의존성 명세 (표준 라이브러리만)
├── .env.example       # 환경 변수 템플릿
├── .gitignore         # Git 제외 파일
└── README.md          # 프로젝트 설명 (이 파일)
```

---

## 🔔 자동 알림 기능

### 🇺🇸 미국장 마감 요약 (매일 미국 동부 16:00 이후)
- 매일 미국장이 끝난 후 당일 시장 흐름을 요약하여 자동으로 전송합니다 (한국 시간 오전 5~6시 경)
- 공포탐욕지수, VIX, 주요 지수(S&P500, NASDAQ, DOW), 환율, 국채수익률 포함

### 🇰🇷 한국장 마감 요약 (매일 한국 15:30 이후)
- 매일 한국장이 끝난 후 (한국 시간 오후 3시 30분 이후) 국내 시장 마감 요약을 자동으로 전송합니다
- **코스피, 코스닥 등락**과 **원/달러 환율**을 중심으로 제공하며, 공포탐욕지수·VIX·미국 주요 지수를 참고 정보로 함께 제공
- 주말 및 한국 공휴일(설날·추석 등)에는 전송하지 않습니다

### 📊 주간 리포트 (매주 월요일 아침 08:00~09:59)
- 매주 월요일 아침에 **지난주(월~금) 주요 지수 및 관심 종목의 주간 변동 요약**을 자동으로 전송합니다
- **주요 지수**: S&P 500, NASDAQ, DOW, KOSPI, KOSDAQ의 주간 변동률
- **관심 종목**: 구독 중인 종목들의 주간 변동률
- **참고 정보**: 공포탐욕지수(1주 전 대비), VIX
- 언제든지 `/weekly` 명령어로 수동 조회 가능

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