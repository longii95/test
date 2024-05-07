import ccxt
import time
import datetime
import telepot
import ntplib
from time import ctime
import pandas as pd
import numpy as np

# 초기 설정

trade_closed = {}  # 각 봉에 대해 거래가 종료되었는지 추적하는 딕셔너리

timeframe_1m = '1m'
timeframe_3m = '3m'
timeframe_1h = '30m'

limit = 500  # 바이낸스에서 읽어오는 데이터 크기
symbol = 'SOL/USDT'  # 거래 symbol

accumulated_profit = 0  # 전역 변수로 총 누적 수익률을 추적

long_active = 0  # 롱 매수 건이 없는 상태
short_active = 0  # 숏 매수건이 없는 상태

entry_price = 0  # 매수가 초기값

position_size = 2000  # 현재 보유한 포지션의 양
initial_position_size = 2000

loss_limit = 0.0075
first_profit_target = 0.0075
second_profit_target = 0.025

real_trading_flag = 0  # if 0, then no real trading, if 1, then go to real trading

# API 키와 비밀번호를 파일에서 불러옵니다.
with open("super_api.txt") as f:
    lines = f.readlines()
    api_key = lines[0].strip()
    secret = lines[1].strip()
    token = lines[2].strip()
    mc = lines[3].strip()

# binance 객체 생성
exchange = ccxt.binance(config={
    'apiKey': api_key,
    'secret': secret,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future'
    }
})

bot = telepot.Bot(token)

print("\n\t[%s][V3-XRP] Trade Start !!!!!!!!!!!!!!!!!!! at %s \n" % (
    symbol, datetime.datetime.now().replace(microsecond=0)))
text = """[%s][V3-XRP] Trade Start !!!!!!!!!!!!!!!!!!! \n[ %s ]\n""" \
       % (symbol, datetime.datetime.now().replace(microsecond=0))
bot.sendMessage(mc, text)


def print_time():
    ntp_client = ntplib.NTPClient()
    response = ntp_client.request(
        'time.windows.com')  # response = ntp_client.request('pool.ntp.org') #  ‘time.google.com’, ‘time.apple.com’, ‘time.nist.gov’ , time.nist.gov
    print(ctime(response.tx_time))


def fetch_data_1m(symbol, timeframe_1m, since, limit):
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe_1m, since, limit)
    df_1m = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df_1m['timestamp'] = pd.to_datetime(df_1m['timestamp'], unit='ms')
    df_1m.set_index('timestamp', inplace=True)
    for timestamp in df_1m.index:
        if timestamp not in trade_closed:
            trade_closed[timestamp] = False  # 초기에는 모든 봉에 대해 거래가 종료되지 않았다고 가정
    return df_1m


def fetch_data_3m(symbol, timeframe_3m, since, limit):
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe_3m, since, limit)
    df_3m = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df_3m['timestamp'] = pd.to_datetime(df_3m['timestamp'], unit='ms')
    df_3m.set_index('timestamp', inplace=True)
    for timestamp in df_3m.index:
        if timestamp not in trade_closed:
            trade_closed[timestamp] = False  # 초기에는 모든 봉에 대해 거래가 종료되지 않았다고 가정
    return df_3m


def fetch_data_1h(symbol, timeframe_1h, since, limit):
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe_1h, since, limit)
    df_1h = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df_1h['timestamp'] = pd.to_datetime(df_1h['timestamp'], unit='ms')
    df_1h.set_index('timestamp', inplace=True)
    for timestamp in df_1h.index:
        if timestamp not in trade_closed:
            trade_closed[timestamp] = False  # 초기에는 모든 봉에 대해 거래가 종료되지 않았다고 가정
    return df_1h


def calculate_bollinger_bands_30_1m(df_1m, n, k):
    df_1m['MA'] = df_1m['close'].rolling(window=n).mean()
    df_1m['STD'] = df_1m['close'].rolling(window=n).std()
    df_1m['Upper_BB_30'] = df_1m['MA'] + (k * df_1m['STD'])
    df_1m['Lower_BB_30'] = df_1m['MA'] - (k * df_1m['STD'])
    return df_1m[['Upper_BB_30', 'Lower_BB_30']]


def calculate_bollinger_bands_30_3m(df_3m, n, k):
    df_3m['MA'] = df_3m['close'].rolling(window=n).mean()
    df_3m['STD'] = df_3m['close'].rolling(window=n).std()
    df_3m['Upper_BB_30'] = df_3m['MA'] + (k * df_3m['STD'])
    df_3m['Lower_BB_30'] = df_3m['MA'] - (k * df_3m['STD'])
    return df_3m[['Upper_BB_30', 'Lower_BB_30']]


def calculate_ema_1m(df_1m, period, column='close'):
    return df_1m[column].ewm(span=period).mean()


def calculate_ema_3m(df_3m, period, column='close'):
    return df_3m[column].ewm(span=period).mean()


def calculate_ema_1h(df_1h, period, column='close'):
    return df_1h[column].ewm(span=period).mean()


def generate_signals(df_1m, df_3m, df_1h):
    # Calculate EMA100 and EMA200 for both timeframes
    df_1m['ema100'] = calculate_ema_1m(df_1m, 100)
    df_1m['ema200'] = calculate_ema_1m(df_1m, 200)

    df_3m['ema100'] = calculate_ema_3m(df_3m, 100)
    df_3m['ema200'] = calculate_ema_3m(df_3m, 200)

    df_1h['ema100'] = calculate_ema_1h(df_1h, 100)
    df_1h['ema200'] = calculate_ema_1h(df_1h, 200)

    # Calculate Bollinger Bands with a period of 30 for both timeframes
    bollinger_bands_30_05_1m = calculate_bollinger_bands_30_1m(df_1m, 21, 0.5)
    df_1m['Upper_BB_30'] = bollinger_bands_30_05_1m['Upper_BB_30']
    df_1m['Lower_BB_30'] = bollinger_bands_30_05_1m['Lower_BB_30']

    bollinger_bands_30_05_3m = calculate_bollinger_bands_30_3m(df_3m, 21, 0.5)
    df_3m['Upper_BB_30'] = bollinger_bands_30_05_3m['Upper_BB_30']
    df_3m['Lower_BB_30'] = bollinger_bands_30_05_3m['Lower_BB_30']

    # Calculate Buy_Signal based on the new conditions
    df_1m['Buy_Signal'] = (
            (df_1m['close'].iloc[-1] > df_1m['Upper_BB_30'].iloc[-1]) &
            (df_1m['Upper_BB_30'].iloc[-1] > df_1m['Lower_BB_30'].iloc[-1]) &
            (df_1m['Lower_BB_30'].iloc[-1] > df_1m['ema100'].iloc[-1]) &
            (df_1m['ema100'].iloc[-1] > df_1m['ema200'].iloc[-1]) &
            (df_3m['close'].iloc[-1] > df_3m['Upper_BB_30'].iloc[-1]) &
            (df_3m['Upper_BB_30'].iloc[-1] > df_3m['Lower_BB_30'].iloc[-1]) &
            (df_3m['Lower_BB_30'].iloc[-1] > df_3m['ema100'].iloc[-1]) &
            (df_3m['ema100'].iloc[-1] > df_3m['ema200'].iloc[-1]) &
            (df_1h['ema100'].iloc[-1] > df_1h['ema200'].iloc[-1]))  # 추가된 조건

    # Calculate Sell_Signal based on the new conditions
    df_1m['Sell_Signal'] = (
            (df_1m['close'].iloc[-1] < df_1m['Lower_BB_30'].iloc[-1]) &
            (df_1m['Lower_BB_30'].iloc[-1] < df_1m['Upper_BB_30'].iloc[-1]) &
            (df_1m['Upper_BB_30'].iloc[-1] < df_1m['ema100'].iloc[-1]) &
            (df_1m['ema100'].iloc[-1] < df_1m['ema200'].iloc[-1]) &
            (df_3m['close'].iloc[-1] < df_3m['Lower_BB_30'].iloc[-1]) &
            (df_3m['Lower_BB_30'].iloc[-1] < df_3m['Upper_BB_30'].iloc[-1]) &
            (df_3m['Upper_BB_30'].iloc[-1] < df_3m['ema100'].iloc[-1]) &
            (df_3m['ema100'].iloc[-1] < df_3m['ema200'].iloc[-1]) &
            (df_1h['ema100'].iloc[-1] < df_1h['ema200'].iloc[-1]))  # 추가된 조건

    return df_1m, df_3m, df_1h


# [LONG] 매수 조건 검사 함수
def check_buy_conditions(df_1m, df_3m):
    # df_1m['ema100'] = calculate_ema_1m(df_1m, 100)
    # df_3m['ema100'] = calculate_ema_3m(df_3m, 100)

    last_candle_timestamp = df_1m.index[-2]
    if trade_closed[last_candle_timestamp]:  # 해당 봉에 대해 거래가 이미 종료되었다면 매수 조건을 확인하지 않음
        return False

    condition = (
        (df_1m['Buy_Signal'].iloc[-1] == 1)
    ).astype(int)

    if condition.all():
        print(f"{datetime.datetime.now().replace(microsecond=0)}\tLONG CASE Passed\n")
    return condition.all()


# [LONG] 매도 조건 검사 함수
def check_long_sell_conditions(df_1m, df_3m, entry_price, long_active, position_size, initial_position_size):
    last_candle_timestamp = df_1m.index[-1]
    current_price = df_1m['close'].iloc[-1]
    # df_1m['ema100'] = calculate_ema_1m(df_1m, 100)  # EMA 100선 계산
    df_3m['ema100'] = calculate_ema_3m(df_3m, 100)  # EMA 100선 계산
    df_1m['ema200'] = calculate_ema_1m(df_1m, 200)  # EMA 100선 계산

    # 종료조건 1
    if long_active == 1 and position_size == initial_position_size and current_price <= entry_price * (1 - loss_limit):
        trade_closed[last_candle_timestamp] = True
        return 'stop_loss'

    # 종료조건 2
    if long_active == 1 and position_size == initial_position_size and current_price >= entry_price * (
            1 + first_profit_target):
        trade_closed[last_candle_timestamp] = True
        return 'partial_sell'

    # 종료조건 3
    if long_active == 1 and position_size == initial_position_size / 2 and (
            current_price <= df_3m['ema100'].iloc[-1] or current_price >= entry_price * (1 + second_profit_target)):
        trade_closed[last_candle_timestamp] = True
        return 'sell_remaining'

    # 종료조건 4
    if long_active == 1 and position_size == initial_position_size and (current_price <= df_3m['ema100'].iloc[-1]):
        trade_closed[last_candle_timestamp] = True
        return 'ema100_sell'

    return None, position_size


# [SHORT] 매도 조건 검사 함수
def check_sell_conditions(df_1m, df_3m):
    #
    # df_1m['ema100'] = calculate_ema_1m(df_1m, 100)
    # df_3m['ema100'] = calculate_ema_3m(df_3m, 100)

    last_candle_timestamp = df_1m.index[-1]  # 이 부분을 추가
    if trade_closed[last_candle_timestamp]:  # 해당 봉에 대해 거래가 이미 종료되었다면 매도 조건을 확인하지 않음
        return False

    condition = (
        (df_1m['Sell_Signal'].iloc[-1] == 1)
    ).astype(int)

    if condition.all():
        print(f"{datetime.datetime.now().replace(microsecond=0)}\tSHORT CASE Passed\n")

    return condition.all()


# [SHORT] 매수 조건 검사 함수
def check_short_buy_conditions(df_1m, df_3m, entry_price, short_active, position_size, initial_position_size):
    last_candle_timestamp = df_1m.index[-1]
    current_price = df_1m['close'].iloc[-1]

    # df_1m['ema100'] = calculate_ema_1m(df_1m, 100)  # EMA 100선 계산
    df_3m['ema100'] = calculate_ema_3m(df_3m, 100)  # EMA 100선 계산
    df_1m['ema200'] = calculate_ema_1m(df_1m, 200)  # EMA 100선 계산

    # 종료조건 1
    if short_active == 1 and position_size == initial_position_size and current_price >= entry_price * (1 + loss_limit):
        trade_closed[last_candle_timestamp] = True
        return 'stop_loss'

    # 종료조건 2
    if short_active == 1 and position_size == initial_position_size and current_price <= entry_price * (
            1 - first_profit_target):
        trade_closed[last_candle_timestamp] = True
        return 'partial_buy'

    # 종료조건 3
    if short_active == 1 and position_size == initial_position_size / 2 and (
            current_price >= df_3m['ema100'].iloc[-1] or current_price <= entry_price * (1 - second_profit_target)):
        trade_closed[last_candle_timestamp] = True
        return 'buy_remaining'

    # 종료조건 3
    if short_active == 1 and position_size == initial_position_size and (current_price >= df_3m['ema100'].iloc[-1]):
        trade_closed[last_candle_timestamp] = True
        return 'ema100_buy'
    return None, position_size


# 수익률 계산 함수
def calculate_profit(current_price, entry_price):
    return (current_price / entry_price) - 1


# 총 누적 수익률 업데이트 함수
def update_accumulated_profit(profit):
    global accumulated_profit
    accumulated_profit += profit  # 현재 수익률을 누적 수익률에 추가


def print_candle_info(df_1m, position_size, entry_price, long_active, short_active):
    # 현재 봉과 이전 봉들의 정보
    last_candle = df_1m.iloc[-1]

    # 수익률 계산
    profit = calculate_profit(last_candle['close'], entry_price) if long_active else 0

    # 출력할 정보
    print("\n")
    print('#' * 100)
    print(
        f"{datetime.datetime.now().replace(microsecond=0)}\t\t\tlong_active = {long_active} :: short_active :: {short_active}")
    print('-' * 100)
    print(
        f"{datetime.datetime.now().replace(microsecond=0)}\t\t\t[LONG]  매수가격 =  {entry_price if long_active else 0} :: 현재 가격 = {last_candle['close']} :: Current Position Size = {position_size if long_active else 0}")
    print(
        f"{datetime.datetime.now().replace(microsecond=0)}\t\t\t[SHORT] 매도가격 =  {entry_price if short_active else 0} :: 현재 가격 = {last_candle['close']} :: Current Position Size = {position_size if short_active else 0}")
    print('-' * 100)

    if accumulated_profit != 0:
        print(
            f"{datetime.datetime.now().replace(microsecond=0)}\t\t\t수익률 = {profit:.2%}\t\t::\t\t누적 수익률 = {accumulated_profit:.2%}")
        print("\n")


# 메인 함수
def main():
    global long_active, short_active, entry_price, position_size, accumulated_profit
    last_print_time = time.time()

    while True:
        current_time = time.time()

        df_1m = fetch_data_1m(symbol, timeframe_1m, None, limit)
        df_3m = fetch_data_3m(symbol, timeframe_3m, None, limit)
        df_1h = fetch_data_1h(symbol, timeframe_1h, None, limit)

        df_1m, df_3m, df_1h = generate_signals(df_1m, df_3m, df_1h)

        if current_time - last_print_time >= 5 * 60:  # 5분마다 시간 동기화
            # print_time()
            last_print_time = current_time

        # 롱 매수 조건 확인
        if not long_active and not short_active and check_buy_conditions(df_1m, df_3m):
            # 롱 매수 실행
            position_size = initial_position_size  # 예시로 100개 매수

            if real_trading_flag == 1:
                order = exchange.create_market_buy_order(
                    symbol=symbol,
                    amount=position_size
                )

            entry_price = df_1m['close'].iloc[-1]
            long_active = 1
            print(f"롱 매수 실행: {entry_price}, 포지션 크기: {position_size}")

            text = """[%s][V3-XRP] [롱 매수 실행] 매수가 = %s :: position size = %s\n[ %s ]\n""" \
                   % (symbol, entry_price, position_size, datetime.datetime.now().replace(microsecond=0))
            bot.sendMessage(mc, text)

        # 롱 거래종료 조건 확인
        if long_active:
            sell_condition = check_long_sell_conditions(df_1m, df_3m, entry_price, long_active, position_size,
                                                        initial_position_size)
            current_price = df_1m['close'].iloc[-1]
            profit = calculate_profit(current_price, entry_price)

            if sell_condition == 'stop_loss':
                # 손절 매도 실행
                if real_trading_flag == 1:
                    order = exchange.create_market_sell_order(
                        symbol=symbol,
                        amount=position_size
                    )

                update_accumulated_profit(profit * 0.995)
                print(f"손절 매도 실행(Stop Loss): {current_price}")

                text = """[%s][V3-XRP] [손절 매도 실행][STOP LOSS] 매도가 = %s :: Accumulated Profit =%s\n[ %s ]\n""" \
                       % (symbol, current_price, accumulated_profit,
                          datetime.datetime.now().replace(microsecond=0))
                bot.sendMessage(mc, text)

                long_active = 0
                position_size = 0  # 포지션 전량 청산
                entry_price = 0  # 진입 가격 업데이트

            elif sell_condition == 'partial_sell' and position_size == initial_position_size:

                position_size = initial_position_size * 0.5

                if real_trading_flag == 1:
                    order = exchange.create_market_sell_order(
                        symbol=symbol,
                        amount=position_size
                    )

                update_accumulated_profit(profit * 0.5)
                print(f"부분 매도 실행: {current_price}, 남은 포지션 크기: {position_size}")
                text = """[%s][V3-XRP] [부분 매도 실행] 매도가 = %s :: Current Position Size = %s :: Accumulated Profit = %s\n[%s]\n""" \
                       % (symbol, current_price, position_size, accumulated_profit,
                          datetime.datetime.now().replace(microsecond=0))
                bot.sendMessage(mc, text)


            elif sell_condition == 'sell_remaining':

                if real_trading_flag == 1:
                    order = exchange.create_market_sell_order(
                        symbol=symbol,
                        amount=position_size
                    )

                update_accumulated_profit(profit * 0.5)
                print(f"잔여 50% 매도 실행: {current_price}, 수익률: {profit:.2%}")
                print("Check point 1-1")

                text = """[%s][V3-XRP] [잔여 매도 실행] 매도가 = %s :: position size = %s :: Accumulated Profit = %s\n[ %s ]\n""" \
                       % (symbol, current_price, position_size, accumulated_profit,
                          datetime.datetime.now().replace(microsecond=0))
                bot.sendMessage(mc, text)
                print("Check point 1-2")

                long_active = 0
                position_size = 0  # 포지션 전량 청산
                entry_price = 0  # 진입 가격 업데이트

        # 숏 매도 조건 확인
        if not short_active and not long_active and check_sell_conditions(df_1m, df_3m):
            # 숏 매도 실행
            entry_price = df_1m['close'].iloc[-1]
            position_size = initial_position_size  # 예시로 100개 매수

            if real_trading_flag == 1:
                order = exchange.create_market_sell_order(
                    symbol=symbol,
                    amount=position_size
                )

            short_active = 1
            print(f"숏 매도 실행: {entry_price}, 포지션 크기: {position_size}")

            text = """[%s][V3-XRP] [숏 매도 실행] 매도가 = %s :: position size = %s \n[ %s ]\n""" \
                   % (symbol, entry_price, position_size, datetime.datetime.now().replace(microsecond=0))
            bot.sendMessage(mc, text)

        # 숏 거래종료 조건 확인
        if short_active:
            buy_condition = check_short_buy_conditions(df_1m, df_3m, entry_price, short_active, position_size,
                                                       initial_position_size)
            current_price = df_1m['close'].iloc[-1]
            profit = calculate_profit(entry_price, current_price)

            if buy_condition == 'stop_loss':
                # 손절 매수 실행
                update_accumulated_profit(profit * 0.995)

                if real_trading_flag == 1:
                    order = exchange.create_market_buy_order(
                        symbol=symbol,
                        amount=position_size
                    )

                print(f"손절 매수 실행: {current_price}")
                text = """[%s][V3-XRP] [손절 매수 실행][Stop Loss] 매수가 = %s :: position size = %s :: Accumulated Profit = %s\n[ %s ]\n""" \
                       % (symbol, current_price, position_size, accumulated_profit,
                          datetime.datetime.now().replace(microsecond=0))
                bot.sendMessage(mc, text)
                short_active = 0
                position_size = 0  # 포지션 전량 청산
                entry_price = 0  # 진입 가격 업데이트

            elif buy_condition == 'partial_buy' and position_size == initial_position_size:
                # 부분 매수 실행
                update_accumulated_profit(profit * 0.5)
                position_size = initial_position_size * 0.5

                if real_trading_flag == 1:
                    order = exchange.create_market_buy_order(
                        symbol=symbol,
                        amount=position_size
                    )

                print(f"부분 매수 실행: {current_price}, 남은 포지션 크기: {position_size}")
                text = """[%s][V3-XRP] [부분 매수 실행] 매수가 = %s :: position size = %s :: Accumulated Profit = %s\n[%s]\n""" \
                       % (symbol, current_price, position_size, accumulated_profit,
                          datetime.datetime.now().replace(microsecond=0))
                bot.sendMessage(mc, text)

            elif buy_condition == 'buy_remaining' and (position_size == initial_position_size * 0.5):
                update_accumulated_profit(profit * 0.5)

                if real_trading_flag == 1:
                    order = exchange.create_market_buy_order(
                        symbol=symbol,
                        amount=position_size
                    )

                print(f"잔여 50% 매수 실행: {current_price}, 수익률: {profit:.2%}")
                print("Check point 2-1")
                text = """[%s][V3-XRP] [잔여 매수 실행] 매수가 = %s :: position size = %s :: Accumulated Profit = %s\n[ %s ]\n""" \
                       % (symbol, current_price, position_size, accumulated_profit,
                          datetime.datetime.now().replace(microsecond=0))
                bot.sendMessage(mc, text)
                print("Check point 2-2")

                short_active = 0
                position_size = 0  # 포지션 전량 청산
                entry_price = 0  # 진입 가격 업데이트

        # 매 30초마다 정보 출력
        if current_time - last_print_time >= 10:
            print_candle_info(df_1m, position_size, entry_price, long_active, short_active)
            last_print_time = current_time

        time.sleep(6)


if __name__ == "__main__":
    main()
    print_time()
