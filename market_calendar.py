"""
미국 시장 휴장일(휴일/주말) 판별 모듈
NYSE(뉴욕증권거래소) 공휴일 규칙 기반으로 미국 증시가 열리는 날인지 판별합니다.

- 주말 (토/일) 제외
- 미국 공휴일 제외 (대체 휴장일 포함)
- 미국 동부 표준시(EST/EDT) 기준 판별
"""

from datetime import datetime, timedelta

# 요일 상수 (datetime.weekday(): Monday=0 ... Sunday=6)
MONDAY = 0
SUNDAY = 6


def _nth_weekday(year, month, weekday, n):
    """해당 월의 n번째 특정 요일의 date를 반환합니다. (예: 3번째 월요일)"""
    first = datetime(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + (n - 1) * 7)


def _last_weekday(year, month, weekday):
    """해당 월의 마지막 특정 요일의 date를 반환합니다. (예: 마지막 월요일)"""
    if month == 12:
        next_month = datetime(year + 1, 1, 1)
    else:
        next_month = datetime(year, month + 1, 1)
    last_day = next_month - timedelta(days=1)
    offset = (last_day.weekday() - weekday) % 7
    return last_day - timedelta(days=offset)


def _easter(year):
    """
    부활절(Easter Sunday) 날짜를 계산합니다.
    Anonymous Gregorian algorithm (Meeus/Jones/Butcher)
    """
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return datetime(year, month, day)


def _get_observed_date(month, day, year):
    """
    고정 공휴일의 실제 증시 휴장일(observed)을 반환합니다.
    NYSE 규칙:
    - 토요일 공휴일 → 전주 금요일 휴장
    - 일요일 공휴일 → 다음주 월요일 휴장
    """
    holiday = datetime(year, month, day)
    if holiday.weekday() == 5:      # 토요일
        return holiday - timedelta(days=1)
    elif holiday.weekday() == 6:    # 일요일
        return holiday + timedelta(days=1)
    return holiday


def _is_observed_market_holiday(date):
    """주어진 날짜가 미국 증시 공휴일(휴장일)인지 확인합니다."""
    year = date.year
    today = date.date()

    # 고정 공휴일 (올해 + 내년 새해 — 토요일이면 올해 12/31 금요일 휴장)
    fixed_holidays = [
        (year, 1, 1),      # New Year's Day
        (year, 6, 19),     # Juneteenth National Independence Day
        (year, 7, 4),      # Independence Day
        (year, 12, 25),    # Christmas Day
        (year + 1, 1, 1),  # 내년 New Year's Day (대체 휴장일이 올해 12/31일 수 있음)
    ]
    for y, m, d in fixed_holidays:
        if _get_observed_date(m, d, y).date() == today:
            return True

    # 요일 기반 공휴일
    weekday_holidays = [
        _nth_weekday(year, 1, MONDAY, 3),    # Martin Luther King Jr. Day: 1월 3번째 월요일
        _nth_weekday(year, 2, MONDAY, 3),    # Presidents' Day: 2월 3번째 월요일
        _last_weekday(year, 5, MONDAY),      # Memorial Day: 5월 마지막 월요일
        _nth_weekday(year, 9, MONDAY, 1),    # Labor Day: 9월 첫 번째 월요일
        _nth_weekday(year, 11, 3, 4),        # Thanksgiving Day: 11월 4번째 목요일
        _easter(year) - timedelta(days=2),   # Good Friday: 부활절 2일 전 금요일
    ]
    for holiday in weekday_holidays:
        if holiday.date() == today:
            return True

    return False


def _is_us_dst(dt):
    """
    UTC 기준 datetime이 미국 일광절약시간(DST)에 해당하는지 판별합니다.
    - DST 시작: 3월 둘째 일요일 02:00 EST (= 07:00 UTC)
    - DST 종료: 11월 첫째 일요일 02:00 EDT (= 06:00 UTC)
    """
    year = dt.year
    dst_start = _nth_weekday(year, 3, SUNDAY, 2).replace(hour=2) + timedelta(hours=5)
    dst_end = _nth_weekday(year, 11, SUNDAY, 1).replace(hour=2) + timedelta(hours=4)
    return dst_start <= dt < dst_end


def get_us_eastern_now():
    """현재 미국 동부 표준시(EST/EDT) 기준 naive datetime을 반환합니다."""
    utc_now = datetime.utcnow()
    offset = -4 if _is_us_dst(utc_now) else -5
    return utc_now + timedelta(hours=offset)


def is_us_trading_day(now_et=None):
    """
    현재(미국 동부 기준)가 미국 증시 거래일인지 확인합니다.
    주말 및 미국 공휴일(대체 휴장일 포함)이면 False를 반환합니다.
    """
    if now_et is None:
        now_et = get_us_eastern_now()

    # 주말 제외
    if now_et.weekday() >= 5:
        return False

    # 공휴일 제외
    if _is_observed_market_holiday(now_et):
        return False

    return True


if __name__ == "__main__":
    now_et = get_us_eastern_now()
    print(f"현재 미국 동부 시간: {now_et.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"미국 거래일 여부: {is_us_trading_day(now_et)}")