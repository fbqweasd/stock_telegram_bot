"""
백테스트 모듈: 실제 predict_buy_sell_prices 로직을 그대로 사용하여
과거 데이터 기반 예측 정확도를 검증합니다.

핵심 설계:
1. Yahoo Finance에서 장기 일봉 데이터(기본 5년)를 가져옵니다.
2. 각 시점에서 그 시점까지의 과거 데이터만 사용하여 predict_buy_sell_prices를 호출합니다.
   (Look-ahead bias 방지: 미래 데이터를 사용하지 않음)
3. 예측 결과(STRONG BUY/BUY/HOLD/SELL/STRONG SELL)와 이후 실제 가격 변동을 비교합니다.
4. 정확도, 승률, 수익률 등 다양한 성능 지표를 계산합니다.

사용법:
    python backtest.py --ticker AAPL --years 5 --horizon 5
    python backtest.py --ticker 005930.KS --years 3 --horizon 10 --step 2
"""

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
import ssl
from datetime import datetime, timedelta

from predictor import predict_buy_sell_prices


# ============================================================
# 데이터 수집 (Yahoo Finance)
# ============================================================

def _make_request(url, retries=3, delay=2):
    """HTTP 요청 헬퍼 (stock_api.py와 동일한 방식)"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=ctx, timeout=15) as response:
                if response.status == 200:
                    return json.loads(response.read().decode("utf-8"))
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(delay)
                continue
            raise e
    return None


def fetch_long_history(ticker, years=5):
    """
    Yahoo Finance에서 장기 일봉 데이터를 가져옵니다.
    range 파라미터로 직접 기간을 지정합니다.

    Returns:
        {
            "ticker": str,
            "timestamps": [int, ...],  # Unix timestamp
            "dates": ["YYYY-MM-DD", ...],
            "closes": [float, ...],
            "highs": [float, ...],
            "lows": [float, ...],
            "opens": [float, ...],
            "volumes": [float, ...],
            "currency": str
        }
        또는 실패 시 None
    """
    ticker = ticker.strip().upper()
    encoded_ticker = urllib.parse.quote(ticker)

    # range 파라미터로 직접 기간 지정 (Yahoo Finance API)
    # 1y, 2y, 5y, 10y, max 지원
    range_map = {
        1: "1y", 2: "2y", 3: "3y", 4: "4y", 5: "5y",
        6: "6y", 7: "7y", 8: "8y", 9: "9y", 10: "10y",
    }
    range_str = range_map.get(years, f"{years}y")
    if years > 10:
        range_str = "max"

    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_ticker}"
        f"?range={range_str}&interval=1d&includePrePost=false"
    )

    data = _make_request(url)
    if not data:
        return None

    try:
        result = data.get("chart", {}).get("result", [{}])[0]
        meta = result.get("meta", {})
        currency = meta.get("currency", "USD")

        timestamps = result.get("timestamp", [])
        quote = result.get("indicators", {}).get("quote", [{}])[0]

        closes = quote.get("close", [])
        highs = quote.get("high", [])
        lows = quote.get("low", [])
        opens = quote.get("open", [])
        volumes = quote.get("volume", [])

        if not timestamps or not closes:
            return None

        # 데이터 정제 (None 값 제거)
        cleaned = {
            "timestamps": [],
            "dates": [],
            "closes": [],
            "highs": [],
            "lows": [],
            "opens": [],
            "volumes": []
        }

        for i in range(len(timestamps)):
            if (i < len(closes) and closes[i] is not None and
                i < len(highs) and highs[i] is not None and
                i < len(lows) and lows[i] is not None and
                i < len(opens) and opens[i] is not None):

                cleaned["timestamps"].append(timestamps[i])
                cleaned["dates"].append(
                    datetime.utcfromtimestamp(timestamps[i]).strftime("%Y-%m-%d")
                )
                cleaned["closes"].append(closes[i])
                cleaned["highs"].append(highs[i])
                cleaned["lows"].append(lows[i])
                cleaned["opens"].append(opens[i])
                cleaned["volumes"].append(
                    volumes[i] if (i < len(volumes) and volumes[i] is not None) else 0
                )

        if len(cleaned["closes"]) < 100:
            return None

        # 최근 N년만 사용
        if years > 0:
            cutoff_ts = time.time() - years * 365 * 24 * 3600
            indices = [i for i, ts in enumerate(cleaned["timestamps"]) if ts >= cutoff_ts]
            if indices:
                start_idx = indices[0]
                for key in ["timestamps", "dates", "closes", "highs", "lows", "opens", "volumes"]:
                    cleaned[key] = cleaned[key][start_idx:]

        cleaned["ticker"] = ticker
        cleaned["currency"] = currency
        return cleaned

    except (IndexError, AttributeError, TypeError) as e:
        print(f"  [오류] 데이터 파싱 실패: {e}")
        return None


# ============================================================
# 백테스트 엔진
# ============================================================

def run_backtest(data, horizon=5, step=1, min_data_points=60,
                 initial_capital=10000, commission_pct=0.0):
    """
    실제 predict_buy_sell_prices 로직을 그대로 사용하는 백테스트.

    각 시점 i에서:
      1. data[0:i+1] (과거 데이터만)으로 predict_buy_sell_prices 호출
      2. 예측 결과(추천, 점수) 기록
      3. 이후 horizon일 뒤 실제 가격과 비교하여 정확도 평가

    Args:
        data: fetch_long_history() 결과
        horizon: 예측 후 며칠 뒤 가격과 비교할지 (기본 5일)
        step: 몇 일 간격으로 예측을 실행할지 (기본 1일 = 매일)
        min_data_points: 지표 계산에 필요한 최소 데이터 수 (기본 60)
        initial_capital: 초기 자본 (기본 10000)
        commission_pct: 수수료율 (기본 0%)

    Returns:
        백테스트 결과 딕셔너리
    """
    closes = data["closes"]
    highs = data["highs"]
    lows = data["lows"]
    opens = data["opens"]
    volumes = data["volumes"]
    dates = data["dates"]
    ticker = data["ticker"]
    currency = data["currency"]

    n = len(closes)
    if n < min_data_points + horizon:
        return {
            "error": f"데이터가 부족합니다. 최소 {min_data_points + horizon}개 봉 필요 (현재 {n}개)"
        }

    # ============================================================
    # 1. 각 시점별 예측 실행
    # ============================================================
    predictions = []  # 각 시점의 예측 결과

    # 지표 계산에 필요한 최소 데이터 수 (MACD: slow(26) + signal(9) = 35, SMA50: 50)
    # 실제 predict 함수는 _last_valid로 마지막 유효 값을 찾으므로
    # 최소 60개 이상이면 안전하게 계산 가능
    start_idx = min_data_points

    for i in range(start_idx, n - horizon):
        if (i - start_idx) % step != 0:
            continue

        # 과거 데이터만 사용 (look-ahead bias 방지)
        stock_data = {
            "ticker": ticker,
            "currency": currency,
            "current_price": closes[i],
            "closes": closes[:i + 1],
            "highs": highs[:i + 1],
            "lows": lows[:i + 1],
            "opens": opens[:i + 1],
            "volumes": volumes[:i + 1],
        }

        try:
            result = predict_buy_sell_prices(stock_data)
        except Exception as e:
            print(f"  [경고] index {i} ({dates[i]}) 예측 실패: {e}")
            continue

        if "error" in result:
            continue

        # 이후 horizon일 뒤 실제 가격
        future_idx = i + horizon
        future_price = closes[future_idx]
        price_change_pct = (future_price - closes[i]) / closes[i] * 100

        # 예측 정확도 평가
        recommendation = result["recommendation"]
        score = result["score"]

        # 매수 신호 → 가격 상승이면 정확
        # 매도 신호 → 가격 하락이면 정확
        # 홀드 → 가격 변동이 작으면 정확
        if recommendation in ("STRONG BUY", "BUY"):
            correct = price_change_pct > 0
            direction = "매수"
        elif recommendation in ("STRONG SELL", "SELL"):
            correct = price_change_pct < 0
            direction = "매도"
        else:  # HOLD
            # 홀드: 가격 변동이 ±2.5% 이내면 정확 (횡보 예측)
            # 수정 1: 5일 기준 ±1%는 너무 엄격하여 ±2.5%로 완화
            correct = abs(price_change_pct) <= 2.5
            direction = "홀드"

        predictions.append({
            "index": i,
            "date": dates[i],
            "future_date": dates[future_idx],
            "price": closes[i],
            "future_price": future_price,
            "price_change_pct": round(price_change_pct, 2),
            "recommendation": recommendation,
            "score": score,
            "confidence": result.get("confidence", 0),
            "direction": direction,
            "correct": correct,
            "buy_target": result.get("buy_target"),
            "sell_target": result.get("sell_target"),
            "stop_loss": result.get("stop_loss"),
            "market_regime": result.get("market_regime"),
        })

    if not predictions:
        return {"error": "예측을 실행할 수 없습니다."}

    # ============================================================
    # 2. 매매 시뮬레이션 (실제 수익률 계산)
    # ============================================================
    # 전략: STRONG BUY/BUY 신호 시 매수, SELL/STRONG SELL 신호 시 매도
    # 매수 후 sell_target 도달 시 익절, stop_loss 도달 시 손절
    capital = initial_capital
    position = 0  # 보유 주식 수
    entry_price = 0
    entry_index = 0
    trades = []
    equity_curve = []
    peak_equity = initial_capital
    max_drawdown = 0

    for p in predictions:
        i = p["index"]
        price = p["price"]
        rec = p["recommendation"]

        if position == 0 and rec in ("STRONG BUY", "BUY"):
            # 매수
            shares = capital / price
            position = shares
            entry_price = price
            capital = 0
            trades.append({
                "type": "BUY",
                "date": p["date"],
                "price": round(price, 2),
                "score": p["score"],
                "confidence": p["confidence"],
            })
        elif position > 0:
            # 보유 중: 익절/손절/시그널 반전 체크
            sell_reason = None

            # 시그널 반전 (매도 신호)
            if rec in ("STRONG SELL", "SELL"):
                sell_reason = "시그널 반전"

            # 익절: sell_target 도달
            if sell_reason is None and p.get("sell_target") and price >= p["sell_target"]:
                sell_reason = "익절 (sell_target 도달)"

            # 손절: stop_loss 도달
            if sell_reason is None and p.get("stop_loss") and price <= p["stop_loss"]:
                sell_reason = "손절 (stop_loss 도달)"

            if sell_reason:
                profit = position * price
                pnl_pct = (price - entry_price) / entry_price * 100
                capital = profit
                trades.append({
                    "type": "SELL",
                    "date": p["date"],
                    "price": round(price, 2),
                    "score": p["score"],
                    "pnl_pct": round(pnl_pct, 2),
                    "reason": sell_reason,
                })
                position = 0

        # 자산 곡선
        equity = capital + (position * price if position > 0 else 0)
        equity_curve.append(equity)
        if equity > peak_equity:
            peak_equity = equity
        drawdown = (peak_equity - equity) / peak_equity * 100 if peak_equity > 0 else 0
        max_drawdown = max(max_drawdown, drawdown)

    # 마지막 포지션 정리
    if position > 0:
        final_price = closes[-1]
        profit = position * final_price
        pnl_pct = (final_price - entry_price) / entry_price * 100
        capital = profit
        trades.append({
            "type": "SELL",
            "date": dates[-1],
            "price": round(final_price, 2),
            "score": 0,
            "pnl_pct": round(pnl_pct, 2),
            "reason": "백테스트 종료 (강제 청산)",
        })

    # ============================================================
    # 3. 성능 지표 계산
    # ============================================================

    # 3-1. 예측 정확도
    total = len(predictions)
    correct_count = sum(1 for p in predictions if p["correct"])
    accuracy = correct_count / total * 100 if total > 0 else 0

    # 추천별 정확도
    rec_stats = {}
    for rec in ["STRONG BUY", "BUY", "HOLD", "SELL", "STRONG SELL"]:
        rec_preds = [p for p in predictions if p["recommendation"] == rec]
        if rec_preds:
            rec_correct = sum(1 for p in rec_preds if p["correct"])
            rec_stats[rec] = {
                "count": len(rec_preds),
                "correct": rec_correct,
                "accuracy_pct": round(rec_correct / len(rec_preds) * 100, 1),
                "avg_price_change_pct": round(
                    sum(p["price_change_pct"] for p in rec_preds) / len(rec_preds), 2
                ),
            }

    # 매수/매도/홀드 방향별 정확도
    direction_stats = {}
    for direction in ["매수", "매도", "홀드"]:
        dir_preds = [p for p in predictions if p["direction"] == direction]
        if dir_preds:
            dir_correct = sum(1 for p in dir_preds if p["correct"])
            direction_stats[direction] = {
                "count": len(dir_preds),
                "correct": dir_correct,
                "accuracy_pct": round(dir_correct / len(dir_preds) * 100, 1),
                "avg_price_change_pct": round(
                    sum(p["price_change_pct"] for p in dir_preds) / len(dir_preds), 2
                ),
            }

    # 3-2. 매매 성과
    closed_trades = [t for t in trades if t["type"] == "SELL"]
    wins = [t for t in closed_trades if t.get("pnl_pct", 0) > 0]
    losses = [t for t in closed_trades if t.get("pnl_pct", 0) <= 0]

    total_return = (capital - initial_capital) / initial_capital * 100 if initial_capital > 0 else 0
    win_rate = len(wins) / len(closed_trades) * 100 if closed_trades else 0

    # 평균 수익/손실
    avg_win = sum(t["pnl_pct"] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t["pnl_pct"] for t in losses) / len(losses) if losses else 0

    # 샤프 비율 (간이)
    returns = [t["pnl_pct"] / 100 for t in closed_trades]
    if len(returns) > 1:
        avg_return = sum(returns) / len(returns)
        variance = sum((r - avg_return) ** 2 for r in returns) / (len(returns) - 1)
        std_dev = variance ** 0.5
        sharpe = avg_return / std_dev if std_dev > 0 else 0
    else:
        sharpe = 0

    # Buy & Hold 비교
    buy_hold_return = (closes[-1] - closes[start_idx]) / closes[start_idx] * 100

    # 3-3. 신뢰도 구간별 정확도
    confidence_buckets = {}
    for bucket_start in [25, 40, 55, 70, 85]:
        bucket_end = bucket_start + 15
        bucket_preds = [
            p for p in predictions
            if bucket_start <= p["confidence"] < bucket_end
        ]
        if bucket_preds:
            bucket_correct = sum(1 for p in bucket_preds if p["correct"])
            confidence_buckets[f"{bucket_start}-{bucket_end}"] = {
                "count": len(bucket_preds),
                "correct": bucket_correct,
                "accuracy_pct": round(bucket_correct / len(bucket_preds) * 100, 1),
            }

    # ============================================================
    # 4. 결과 반환
    # ============================================================
    return {
        "ticker": ticker,
        "currency": currency,
        "period": {
            "start_date": dates[start_idx],
            "end_date": dates[-1],
            "total_days": n,
            "test_days": len(predictions),
        },
        "settings": {
            "horizon_days": horizon,
            "step_days": step,
            "min_data_points": min_data_points,
            "initial_capital": initial_capital,
            "commission_pct": commission_pct,
        },
        "prediction_accuracy": {
            "total_predictions": total,
            "correct_predictions": correct_count,
            "accuracy_pct": round(accuracy, 1),
            "by_recommendation": rec_stats,
            "by_direction": direction_stats,
            "by_confidence": confidence_buckets,
        },
        "trading_performance": {
            "initial_capital": initial_capital,
            "final_capital": round(capital, 2),
            "total_return_pct": round(total_return, 2),
            "buy_hold_return_pct": round(buy_hold_return, 2),
            "num_trades": len(closed_trades),
            "win_rate_pct": round(win_rate, 1),
            "avg_win_pct": round(avg_win, 2),
            "avg_loss_pct": round(avg_loss, 2),
            "profit_factor": round(sum(t["pnl_pct"] for t in wins) / abs(sum(t["pnl_pct"] for t in losses)), 2) if losses and sum(t["pnl_pct"] for t in losses) != 0 else 0,
            "max_drawdown_pct": round(max_drawdown, 2),
            "sharpe_ratio": round(sharpe, 2),
        },
        "recent_trades": trades[-10:],
        "recent_predictions": predictions[-10:],
    }


# ============================================================
# 결과 출력
# ============================================================

def print_report(result):
    """백테스트 결과를 보기 좋게 출력합니다."""
    if "error" in result:
        print(f"\n[오류] {result['error']}")
        return

    ticker = result["ticker"]
    currency = result["currency"]
    period = result["period"]
    settings = result["settings"]
    pred_acc = result["prediction_accuracy"]
    trade_perf = result["trading_performance"]

    print("=" * 70)
    print(f"  백테스트 결과: {ticker} ({currency})")
    print("=" * 70)
    print(f"  기간: {period['start_date']} ~ {period['end_date']}")
    print(f"  전체 데이터: {period['total_days']}일, 테스트: {period['test_days']}일")
    print(f"  예측 후 비교: {settings['horizon_days']}일 뒤, 예측 간격: {settings['step_days']}일")
    print()

    # 예측 정확도
    print("-" * 70)
    print("  [예측 정확도]")
    print("-" * 70)
    print(f"  전체 예측: {pred_acc['total_predictions']}회")
    print(f"  정확: {pred_acc['correct_predictions']}회")
    print(f"  정확도: {pred_acc['accuracy_pct']}%")
    print()

    print("  [추천별 정확도]")
    print(f"  {'추천':<12} {'횟수':>6} {'정확':>6} {'정확도':>8} {'평균 변동':>10}")
    print(f"  {'-'*50}")
    for rec, stats in pred_acc["by_recommendation"].items():
        print(f"  {rec:<12} {stats['count']:>6} {stats['correct']:>6} "
              f"{stats['accuracy_pct']:>7}% {stats['avg_price_change_pct']:>9}%")
    print()

    print("  [방향별 정확도]")
    print(f"  {'방향':<8} {'횟수':>6} {'정확':>6} {'정확도':>8} {'평균 변동':>10}")
    print(f"  {'-'*45}")
    for direction, stats in pred_acc["by_direction"].items():
        print(f"  {direction:<8} {stats['count']:>6} {stats['correct']:>6} "
              f"{stats['accuracy_pct']:>7}% {stats['avg_price_change_pct']:>9}%")
    print()

    # 매매 성과
    print("-" * 70)
    print("  [매매 성과]")
    print("-" * 70)
    print(f"  초기 자본: {trade_perf['initial_capital']:,} {currency}")
    print(f"  최종 자본: {trade_perf['final_capital']:,.2f} {currency}")
    print(f"  총 수익률: {trade_perf['total_return_pct']}%")
    print(f"  Buy & Hold: {trade_perf['buy_hold_return_pct']}%")
    print(f"  거래 횟수: {trade_perf['num_trades']}회")
    print(f"  승률: {trade_perf['win_rate_pct']}%")
    print(f"  평균 수익: {trade_perf['avg_win_pct']}%")
    print(f"  평균 손실: {trade_perf['avg_loss_pct']}%")
    print(f"  Profit Factor: {trade_perf['profit_factor']}")
    print(f"  최대 낙폭: {trade_perf['max_drawdown_pct']}%")
    print(f"  샤프 비율: {trade_perf['sharpe_ratio']}")
    print()

    # 최근 거래
    if result.get("recent_trades"):
        print("-" * 70)
        print("  [최근 거래]")
        print("-" * 70)
        print(f"  {'날짜':<12} {'유형':<6} {'가격':>10} {'수익률':>8} {'사유':<20}")
        print(f"  {'-'*60}")
        for t in result["recent_trades"]:
            pnl = f"{t.get('pnl_pct', 0):>7}%" if t["type"] == "SELL" else "     -"
            reason = t.get("reason", "") if t["type"] == "SELL" else ""
            print(f"  {t['date']:<12} {t['type']:<6} {t['price']:>10.2f} {pnl} {reason:<20}")
        print()

    # 최근 예측
    if result.get("recent_predictions"):
        print("-" * 70)
        print("  [최근 예측]")
        print("-" * 70)
        print(f"  {'날짜':<12} {'추천':<12} {'점수':>6} {'신뢰도':>6} {'현재가':>10} {'미래가':>10} {'변동':>8} {'정확':>5}")
        print(f"  {'-'*75}")
        for p in result["recent_predictions"]:
            mark = "O" if p["correct"] else "X"
            print(f"  {p['date']:<12} {p['recommendation']:<12} {p['score']:>6.2f} "
                  f"{p['confidence']:>5}% {p['price']:>10.2f} {p['future_price']:>10.2f} "
                  f"{p['price_change_pct']:>7}% {mark:>5}")
    print("=" * 70)


# ============================================================
# 메인
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="주식 매수/매도 타이밍 예측 백테스트",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python backtest.py --ticker AAPL
  python backtest.py --ticker 005930.KS --years 3 --horizon 10
  python backtest.py --ticker TSLA --years 5 --horizon 5 --step 2 --json
        """
    )
    parser.add_argument("--ticker", "-t", required=True, help="종목 티커 (예: AAPL, 005930.KS)")
    parser.add_argument("--years", "-y", type=int, default=5, help="백테스트 기간 (년, 기본 5)")
    parser.add_argument("--horizon", "-H", type=int, default=5,
                        help="예측 후 며칠 뒤 가격과 비교할지 (기본 5일)")
    parser.add_argument("--step", "-s", type=int, default=1,
                        help="몇 일 간격으로 예측을 실행할지 (기본 1일 = 매일)")
    parser.add_argument("--capital", "-c", type=float, default=10000,
                        help="초기 자본 (기본 10000)")
    parser.add_argument("--json", action="store_true",
                        help="JSON 형식으로 결과 출력")
    parser.add_argument("--output", "-o", help="결과를 JSON 파일로 저장할 경로")

    args = parser.parse_args()

    print(f"\n[1/3] 데이터 수집 중... ({args.ticker}, {args.years}년)")
    data = fetch_long_history(args.ticker, years=args.years)

    if not data:
        print(f"  [오류] {args.ticker} 데이터를 가져올 수 없습니다.")
        sys.exit(1)

    print(f"  데이터 수집 완료: {len(data['closes'])}일 "
          f"({data['dates'][0]} ~ {data['dates'][-1]})")

    print(f"\n[2/3] 백테스트 실행 중... (horizon={args.horizon}일, step={args.step}일)")
    result = run_backtest(
        data,
        horizon=args.horizon,
        step=args.step,
        initial_capital=args.capital,
    )

    if "error" in result:
        print(f"  [오류] {result['error']}")
        sys.exit(1)

    print(f"  백테스트 완료: {result['prediction_accuracy']['total_predictions']}회 예측")

    print(f"\n[3/3] 결과 출력")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_report(result)

    # JSON 파일 저장
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n결과가 {args.output}에 저장되었습니다.")


if __name__ == "__main__":
    main()