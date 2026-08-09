# 📁 프로젝트 파일 구조

> **프로젝트**: 텔레그램 주식 알림 봇 (Stock Alert Telegram Bot)
> **경로**: `d:\workspace\stock_bot` (Git 브랜치: `main`)
> **작성일**: 2026-08-09

---

## 📂 디렉터리 트리

```
stock_bot/
│
│  # =========================================
│  # 📄 루트 설정 파일
│  # =========================================
├── .env.example                  # 환경 변수 템플릿 (copy → .env)
├── .gitignore                    # Git 제외 목록 (data/, results*, __pycache__ 등)
├── README.md                     # 프로젝트 설명서 (기능/명령어/백테스트 사용법)
├── requirements.txt              # 의존성 명세 (표준 라이브러리만 - 외부 패키지 없음)
├── Dockerfile                    # Docker 이미지 빌드 (python:3.11-slim, TZ=Asia/Seoul)
│
│  # =========================================
│  # 🐍 핵심 Python 모듈 (알파벳 순)
│  # =========================================
├── config.py                     # [40줄]  .env 로드 & 전역 설정 정의
│                                 #   - TELEGRAM_BOT_TOKEN, CHECK_INTERVAL
│                                 #   - DB_PATH, MAX_DAILY_RECOMMENDATION_ALERTS
│
├── database.py                   # [540줄] SQLite 데이터베이스 계층 (표준 sqlite3)
│                                 #   - 테이블: subscriptions, last_signals, last_prices,
│                                 #     daily_price_alerts, chat_topics, chat_alert_settings,
│                                 #     high_breakout_alerts, weekly_report_sends,
│                                 #     recommendation_alerts
│                                 #   - 구독 관리 / 시그널 중복 방지 / 가격 추적 / 알림 제한 기록
│
├── indicators.py                 # [368줄] 기술적 지표 계산 (외부 라이브러리 없음)
│                                 #   - calculate_sma / calculate_ema
│                                 #   - calculate_bollinger_bands / calculate_rsi (Wilder)
│                                 #   - calculate_macd / calculate_momentum / calculate_atr
│                                 #   - calculate_volume_trend / find_support_resistance
│                                 #   - detect_market_regime (추세장/횡보장)
│
├── main.py                       # [70줄]  엔트리 포인트
│                                 #   - 환경 체크 → DB 초기화 → 봇 폴링 시작
│                                 #   → 스케줄러 시작 → graceful shutdown 처리
│
├── market_calendar.py            # [222줄] 거래일(휴장일) 판별 모듈
│                                 #   - 미국: NYSE 공휴일 규칙(고정/요일 기반/부활절/DST)
│                                 #   - 한국: 양력 공휴일 + 음력(설날/추석/부처님오신날, ~2029) + 대체공휴일
│                                 #   - get_us_eastern_now / get_korea_now
│                                 #   - is_us_trading_day / is_korea_trading_day
│
├── market_indices.py             # [1172줄] 시장 인덱스/거시 데이터 수집
│                                 #   - 공포탐욕지수 (CNN Money 공식 API)
│                                 #   - VIX(^VIX), S&P500(^GSPC), NASDAQ(^IXIC), DOW(^DJI)
│                                 #   - KOSPI(^KS11), KOSDAQ(^KQ11)
│                                 #   - USD/KRW(환율), 미국 10년물 국채(^TNX), 달러 인덱스(DXY)
│                                 #   - 지수 역대/52주 최고가, 극단 조건 감지, 리포트 포맷팅
│
├── predictor.py                  # [589줄] 매수/매도 가격 예측 (규칙 기반 휴리스틱)
│                                 #   - RSI, MACD, 볼린저, SMA20/50, 거래량, 지지/저항, ATR, 시장 국면
│                                 #   - 지표별 가중치 점수화 (-2 ~ +2)
│                                 #   - STRONG BUY/BUY/HOLD/SELL/STRONG SELL 5단계 추천
│                                 #   - ATR 기반 매수/매도 목표가 & 손절가 산출
│
├── scheduler.py                  # [773줄] 백그라운드 알림 스케줄러 (threading)
│                                 #   - CHECK_INTERVAL 주기로 전체 구독 종목 스캔
│                                 #   - 기술적 이벤트 알림 (볼린저/SMA20·60·120/RSI)
│                                 #   - 가격 변동 알림, 신고가 돌파, 극단 시장 조건,
│                                 #     미국/한국장 마감 요약, 주간 리포트
│                                 #   - STRONG BUY/SELL 권장 알림 (하루 최대 3회)
│
├── stock_api.py                  # [747줄] Yahoo Finance API 연동 (urllib, 재시도 포함)
│                                 #   - 1분봉/5분봉/일봉/주봉 데이터 수집 (프리/애프터장 포함)
│                                 #   - 현재가, 전일종가, 종목명, 통화 판별
│                                 #   - 역대/52주 최고가, 주간 변동률
│
├── telegram_bot.py               # [1232줄] 텔레그램 봇 (Long Polling, urllib)
│                                 #   - setMyCommands로 명령어 자동완성 등록
│                                 #   - 명령어 디스패치 (영문 + 한글 별칭 + 단축어)
│                                 #   - 단체방 Topics(스레드) 대응, 답장(reply) 지원
│                                 #   - /predict, /predict_short(5분봉), /predict_weekly(주봉)
│
├── weekly_report.py              # [141줄] 주간 리포트 생성 모듈
│                                 #   - 지난주(월~금) 범위 계산
│                                 #   - 주요 지수/관심 종목 주간 변동 + 공포·VIX 참고 정보
│                                 #   - HTML 포맷 리포트 생성
│
│  # =========================================
│  # 🔬 백테스트
│  # =========================================
├── backtest.py                   # [571줄] 예측 정확도 백테스트 CLI
│                                 #   - `--ticker --years --horizon --step --capital --json --output`
│                                 #   - 과거 데이터만 사용 (Look-ahead bias 방지)
│                                 #   - 정확도/승률/수익률/PF/MDD/샤프 등 지표 산출
│
├── backtest_strong_alerts.py     # [427줄] STRONG BUY/SELL "무조건 액션" 전략 백테스트
│                                 #   - 12개 종목 자동 순회 (성향별: 기술주/성장주/방어주/에너지/한국주)
│                                 #   - 매수/매도 권장 알림 전략의 실질 수익률 검증
│
│  # =========================================
│  # 🗄️ 데이터
│  # =========================================
├── data/                         # (Git 제외)
│   └── stock_bot.db              #   SQLite 데이터베이스 파일
│
│  # =========================================
│  # ✅ 단위 테스트
│  # =========================================
└── tests/                        # python -m unittest discover -s tests -v
    ├── test_alert_settings.py        # [19줄]   자동알림 on/off 설정 테스트
    ├── test_backtest.py              # [282줄]  백테스트 (데이터 수집/실행/Look-ahead 방지)
    ├── test_korea_market_close.py    # [72줄]   한국 휴장일 판별 + 마감 리포트 포맷
    ├── test_recommendation_alerts.py # [206줄]  STRONG BUY/SELL 권장 알림 (DB/제한/전송)
    └── test_scheduler_trading_day.py # [106줄]  휴장일 스캔 스킵 검증
```

---

## 🔍 모듈 의존성 구성도

```
                     ┌──────────────────────────┐
                     │         main.py          │  (엔트리 포인트)
                     └─────────────┬────────────┘
          ┌────────────────────────┴────────────────────────┐
          ▼                                                  ▼
   ┌──────────────┐                                  ┌──────────────┐
   │ telegram_bot │  ◀────────── 사용자 명령/알림 ──▶ │   scheduler  │
   └──────┬───────┘                                  └──────┬───────┘
          │                                                │
          ▼                                                ▼
   ┌──────────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────┐
   │ predictor.py │◀──│ indicators│   │ stock_api│──▶│ Yahoo Finance │
   │ (예측/추천)   │   │ (지표계산) │   │ (데이터수집)│   └──────────────┘
   └──────────────┘   └──────────┘   └─────┬────┘
                                           │
   ┌──────────────┐   ┌──────────┐   ┌─────▼────┐   ┌──────────────┐
   │market_indices│◀──│ market_   │──▶│ database │   │ weekly_report│
   │ (지수/거시)   │   │ calendar  │   │ (SQLite)  │   │ (주간 요약)  │
   └──────────────┘   └──────────┘   └──────────┘   └──────────────┘

   ┌──────────────┐   ┌─────────────────────┐
   │   backtest   │──▶│  predictor 재사용     │  (오프라인 검증 도구)
   └──────────────┘   └─────────────────────┘
```

- **config.py**: 모든 모듈의 공통 설정 (최하단 레이어)
- **database.py**: scheduler / telegram_bot / weekly_report가 공통 사용
- **indicators.py**: predictor와 scheduler가 공통 사용
- **stock_api.py, market_indices.py, market_calendar.py**: 데이터 수집/판별 담당
- **backtest.py → predictor.py**: 실제 운영 로직(`predict_buy_sell_prices`)을 그대로 재사용하는 설계

---

## 📌 참고 (Git 제외 대상)

| 항목 | 비고 |
|------|------|
| `data/` | SQLite DB (런타임 생성) |
| `results/`, `results_v2/` | 백테스트 결과물 (`.gitignore`에 `results*` 등록) |
| `.env` | 봇 토큰 등 비밀값 |
| `__pycache__/` | Python 캐시 |