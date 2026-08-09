"""
강한 매수(STRONG BUY) / 강한 매도(STRONG SELL) 알림 전략 백테스트

전략 규칙:
- STRONG BUY 신호 발생 시: 무조건 매수 (현금 보유 시)
- STRONG SELL 신호 발생 시: 무조건 매도 (주식 보유 시)
- BUY / SELL / HOLD 신호는 무시 (액션 취하지 않음)

기존 backtest.py의 run_backtest와 달리 STRONG 신호에만 반응하는
"무조건 액션" 전략의 성과를 검증합니다.

사용법:
    python backtest_strong_alerts.py
"""

import json
import sys
import time
from datetime import datetime

from backtest import fetch_long_history
from predictor import predict_buy_sell_prices


def run_strong_alert_backtest(data, horizon=5, step=1, min_data_points=60,
                              initial_capital=10000, commission_pct=0.0):
    """
    STRONG BUY / STRONG SELL 신호에 무조건 액션을 취하는 백테스트.

    각 시점 i에서:
      1. data[0:i+1] (과거 데이터만)으로 predict_buy_sell_prices 호출
      2. STRONG BUY → 매수, STRONG SELL → 매도 (무조건 액션)
      3. 이후 horizon일 뒤 가격과 비교하여 정확도 평가

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
    timestamps = data["timestamps"]
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

        # STRONG BUY → 가격 상승이면 정확
        # STRONG SELL → 가격 하락이면 정확
        if recommendation == "STRONG BUY":
            correct = price_change_pct > 0
            direction = "강한 매수"
        elif recommendation == "STRONG SELL":
            correct = price_change_pct < 0
            direction = "강한 매도"
        else:
            correct = None  # 액션 없음
            direction = "무시"

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
    # 2. 매매 시뮬레이션 (STRONG 신호에 무조건 액션)
    # ============================================================
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

        if position == 0 and rec == "STRONG BUY":
            # 무조건 매수
            shares = capital / price
            position = shares
            entry_price = price
            entry_index = i
            capital = 0
            trades.append({
                "type": "BUY",
                "date": p["date"],
                "price": round(price, 2),
                "score": p["score"],
                "confidence": p["confidence"],
                "signal": "STRONG BUY",
            })
        elif position > 0 and rec == "STRONG SELL":
            # 무조건 매도
            profit = position * price
            pnl_pct = (price - entry_price) / entry_price * 100
            capital = profit
            trades.append({
                "type": "SELL",
                "date": p["date"],
                "price": round(price, 2),
                "score": p["score"],
                "pnl_pct": round(pnl_pct, 2),
                "reason": "STRONG SELL 신호 (무조건 매도)",
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

    # 3-1. STRONG 신호 정확도
    strong_preds = [p for p in predictions if p["correct"] is not None]
    strong_buy_preds = [p for p in predictions if p["recommendation"] == "STRONG BUY"]
    strong_sell_preds = [p for p in predictions if p["recommendation"] == "STRONG SELL"]

    strong_buy_correct = sum(1 for p in strong_buy_preds if p["correct"])
    strong_sell_correct = sum(1 for p in strong_sell_preds if p["correct"])

    strong_buy_accuracy = strong_buy_correct / len(strong_buy_preds) * 100 if strong_buy_preds else 0
    strong_sell_accuracy = strong_sell_correct / len(strong_sell_preds) * 100 if strong_sell_preds else 0

    # STRONG 신호 후 평균 가격 변동
    strong_buy_avg_change = sum(p["price_change_pct"] for p in strong_buy_preds) / len(strong_buy_preds) if strong_buy_preds else 0
    strong_sell_avg_change = sum(p["price_change_pct"] for p in strong_sell_preds) / len(strong_sell_preds) if strong_sell_preds else 0

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
            "strategy": "STRONG BUY/SELL 신호에 무조건 액션",
        },
        "strong_signal_stats": {
            "total_strong_signals": len(strong_preds),
            "strong_buy_count": len(strong_buy_preds),
            "strong_buy_correct": strong_buy_correct,
            "strong_buy_accuracy_pct": round(strong_buy_accuracy, 1),
            "strong_buy_avg_price_change_pct": round(strong_buy_avg_change, 2),
            "strong_sell_count": len(strong_sell_preds),
            "strong_sell_correct": strong_sell_correct,
            "strong_sell_accuracy_pct": round(strong_sell_accuracy, 1),
            "strong_sell_avg_price_change_pct": round(strong_sell_avg_change, 2),
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


def print_report(result):
    """백테스트 결과를 보기 좋게 출력합니다."""
    if "error" in result:
        print(f"\n[오류] {result['error']}")
        return

    ticker = result["ticker"]
    currency = result["currency"]
    period = result["period"]
    settings = result["settings"]
    strong_stats = result["strong_signal_stats"]
    trade_perf = result["trading_performance"]

    print("=" * 70)
    print(f"  STRONG 알림 백테스트: {ticker} ({currency})")
    print("=" * 70)
    print(f"  전략: {settings['strategy']}")
    print(f"  기간: {period['start_date']} ~ {period['end_date']}")
    print(f"  전체 데이터: {period['total_days']}일, 테스트: {period['test_days']}일")
    print(f"  예측 후 비교: {settings['horizon_days']}일 뒤, 예측 간격: {settings['step_days']}일")
    print()

    # STRONG 신호 통계
    print("-" * 70)
    print("  [STRONG 신호 통계]")
    print("-" * 70)
    print(f"  총 STRONG 신호: {strong_stats['total_strong_signals']}회")
    print(f"  STRONG BUY: {strong_stats['strong_buy_count']}회 "
          f"(정확 {strong_stats['strong_buy_correct']}회, "
          f"정확도 {strong_stats['strong_buy_accuracy_pct']}%, "
          f"평균 변동 {strong_stats['strong_buy_avg_price_change_pct']}%)")
    print(f"  STRONG SELL: {strong_stats['strong_sell_count']}회 "
          f"(정확 {strong_stats['strong_sell_correct']}회, "
          f"정확도 {strong_stats['strong_sell_accuracy_pct']}%, "
          f"평균 변동 {strong_stats['strong_sell_avg_price_change_pct']}%)")
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
    print("=" * 70)


def main():
    # 각기 성향이 다른 12개 종목
    tickers = [
        # 대형 기술주 (성장 + 가치)
        ("AAPL", "애플 (대형 기술주)"),
        ("MSFT", "마이크로소프트 (대형 기술주)"),
        ("GOOGL", "알파벳 (대형 기술주)"),
        # 고성장 / 고변동성
        ("NVDA", "엔비디아 (고성장 반도체)"),
        ("TSLA", "테슬라 (고변동성 성장주)"),
        ("AMZN", "아마존 (대형 성장주)"),
        # 방어적 / 저변동성
        ("JNJ", "존슨앤존슨 (방어적 헬스케어)"),
        ("KO", "코카콜라 (방어적 소비재)"),
        ("PG", "프록터앤갬블 (방어적 소비재)"),
        # 경기순환 / 에너지
        ("XOM", "엑슨모빌 (에너지)"),
        # 한국 대형주
        ("005930.KS", "삼성전자 (한국 대형주)"),
        ("000660.KS", "SK하이닉스 (한국 반도체)"),
    ]

    years = 5
    horizon = 5
    step = 1
    initial_capital = 10000

    all_results = []

    print("=" * 70)
    print("  강한 매수/강한 매도 알림 무조건 액션 전략 백테스트")
    print("=" * 70)
    print(f"  기간: 최근 {years}년, horizon: {horizon}일, step: {step}일")
    print(f"  초기 자본: {initial_capital:,}")
    print(f"  전략: STRONG BUY → 무조건 매수, STRONG SELL → 무조건 매도")
    print("=" * 70)

    for i, (ticker, desc) in enumerate(tickers, 1):
        print(f"\n[{i}/12] {ticker} ({desc}) - 데이터 수집 중...")
        data = fetch_long_history(ticker, years=years)

        if not data:
            print(f"  [오류] {ticker} 데이터를 가져올 수 없습니다.")
            all_results.append({
                "ticker": ticker,
                "name": desc,
                "error": "데이터 수집 실패"
            })
            continue

        print(f"  데이터 수집 완료: {len(data['closes'])}일 "
              f"({data['dates'][0]} ~ {data['dates'][-1]})")

        print(f"  백테스트 실행 중...")
        result = run_strong_alert_backtest(
            data,
            horizon=horizon,
            step=step,
            initial_capital=initial_capital,
        )

        if "error" in result:
            print(f"  [오류] {result['error']}")
            all_results.append({
                "ticker": ticker,
                "name": desc,
                "error": result["error"]
            })
            continue

        result["name"] = desc
        all_results.append(result)

        # 개별 결과 출력
        print_report(result)

        # API 호출 간격 (rate limit 방지)
        if i < len(tickers):
            time.sleep(1)

    # ============================================================
    # 종합 요약
    # ============================================================
    print("\n\n")
    print("=" * 100)
    print("  [종합 요약] - 12개 종목 STRONG 알림 무조건 액션 전략")
    print("=" * 100)

    valid_results = [r for r in all_results if "error" not in r]

    # 요약 테이블
    print(f"\n  {'종목':<12} {'STRONG BUY':>10} {'BUY 정확도':>10} {'STRONG SELL':>11} {'SELL 정확도':>11} "
          f"{'수익률':>8} {'Buy&Hold':>9} {'승률':>6} {'거래':>5} {'최대낙폭':>8}")
    print(f"  {'-'*100}")

    for r in valid_results:
        ss = r["strong_signal_stats"]
        tp = r["trading_performance"]
        print(f"  {r['ticker']:<12} {ss['strong_buy_count']:>10} {ss['strong_buy_accuracy_pct']:>9}% "
              f"{ss['strong_sell_count']:>11} {ss['strong_sell_accuracy_pct']:>10}% "
              f"{tp['total_return_pct']:>7}% {tp['buy_hold_return_pct']:>8}% "
              f"{tp['win_rate_pct']:>5}% {tp['num_trades']:>5} {tp['max_drawdown_pct']:>7}%")

    # 평균 통계
    if valid_results:
        avg_buy_acc = sum(r["strong_signal_stats"]["strong_buy_accuracy_pct"] for r in valid_results) / len(valid_results)
        avg_sell_acc = sum(r["strong_signal_stats"]["strong_sell_accuracy_pct"] for r in valid_results) / len(valid_results)
        avg_return = sum(r["trading_performance"]["total_return_pct"] for r in valid_results) / len(valid_results)
        avg_bh = sum(r["trading_performance"]["buy_hold_return_pct"] for r in valid_results) / len(valid_results)
        avg_win_rate = sum(r["trading_performance"]["win_rate_pct"] for r in valid_results) / len(valid_results)
        total_trades = sum(r["trading_performance"]["num_trades"] for r in valid_results)

        print(f"  {'-'*100}")
        print(f"  {'평균':<12} {'':>10} {avg_buy_acc:>9.1f}% {'':>11} {avg_sell_acc:>10.1f}% "
              f"{avg_return:>7.1f}% {avg_bh:>8.1f}% {avg_win_rate:>5.1f}% {total_trades:>5}")

        # 전략 vs Buy&Hold 비교
        better_than_bh = sum(1 for r in valid_results if r["trading_performance"]["total_return_pct"] > r["trading_performance"]["buy_hold_return_pct"])
        print(f"\n  전략이 Buy&Hold보다 우수한 종목: {better_than_bh}/{len(valid_results)}")

        # STRONG 신호 정확도 종합
        total_strong_buy = sum(r["strong_signal_stats"]["strong_buy_count"] for r in valid_results)
        total_strong_buy_correct = sum(r["strong_signal_stats"]["strong_buy_correct"] for r in valid_results)
        total_strong_sell = sum(r["strong_signal_stats"]["strong_sell_count"] for r in valid_results)
        total_strong_sell_correct = sum(r["strong_signal_stats"]["strong_sell_correct"] for r in valid_results)

        print(f"\n  [STRONG 신호 종합]")
        print(f"  STRONG BUY: {total_strong_buy}회 중 {total_strong_buy_correct}회 정확 "
              f"({total_strong_buy_correct/total_strong_buy*100:.1f}%)" if total_strong_buy else "  STRONG BUY: 없음")
        print(f"  STRONG SELL: {total_strong_sell}회 중 {total_strong_sell_correct}회 정확 "
              f"({total_strong_sell_correct/total_strong_sell*100:.1f}%)" if total_strong_sell else "  STRONG SELL: 없음")

    # JSON 저장
    output_file = "results/strong_alert_backtest_results.json"
    import os
    os.makedirs("results", exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n\n전체 결과가 {output_file}에 저장되었습니다.")


if __name__ == "__main__":
    main()