import os
import pandas as pd
from binance.client import Client
import ta
import time
import logging
from dotenv import load_dotenv
from binance.helpers import round_step_size

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

load_dotenv()

# Configuración de la API de Binance
api_key = os.getenv('BINANCE_API_KEY')
api_secret = os.getenv('BINANCE_API_SECRET')

# Validar la lectura de las claves
if not api_key or not api_secret:
    raise ValueError("Las claves de la API no están configuradas correctamente en el entorno.")

client = Client(api_key, api_secret)

# Function to get account balance
def get_balance(asset):
    try:
        balance = client.get_asset_balance(asset=asset)
        return float(balance['free'])
    except Exception as e:
        print(f"Error fetching {asset} balance: {e}")
        return 0.0
        
# Función para obtener datos históricos de Binance
def get_historical_data(symbol, interval, start_str):
    try:
        klines = client.get_historical_klines(symbol, interval, start_str)
        df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        df = df.astype(float)
        return df
    except Exception as e:
        logging.error(f"Error fetching historical data: {e}")
        return pd.DataFrame()

# Función para aplicar la estrategia de cruce de medias móviles
def apply_strategy(df):
    df['SMA50'] = df['close'].rolling(window=50).mean()
    df['SMA200'] = df['close'].rolling(window=200).mean()
    
    df['Signal'] = 0
    
    df.loc[df['SMA50'] > df['SMA200'], 'Signal'] = 1
    df.loc[df['SMA50'] <= df['SMA200'], 'Signal'] = -1
    
    df['Position'] = df['Signal'].shift()
    return df

# Función para colocar órdenes en Binance
def place_order(symbol, quantity, side, order_type='MARKET'):
    try:
        logging.info(f"Placing {side} order for {quantity} of {symbol}")
        order = client.create_order(
            symbol=symbol,
            side=side,
            type=order_type,
            quantity=quantity
        )
        logging.info(order)
    except Exception as e:
        logging.error(f"Error placing order: {e}")

# Función para ejecutar órdenes de compra y venta
def execute_trades(df, symbol, balance):
    for index, row in df.iterrows():
        if row['Position'] == 1 and row['Signal'] == 1:  # Buy
            quantity = balance / row['close']
            place_order(symbol, quantity, 'BUY')
        elif row['Position'] == -1 and row['Signal'] == -1:  # Sell
            quantity = balance / row['close']
            place_order(symbol, quantity, 'SELL')

# Función para colocar órdenes con gestión de riesgo
def get_symbol_info(symbol):
    try:
        info = client.get_symbol_info(symbol)
        return info
    except Exception as e:
        logging.error(f"Error fetching symbol info: {e}")
        return None
    
def get_quantity_precision(symbol):
    info = get_symbol_info(symbol)
    if info:
        return info['baseAssetPrecision']
    return None

# Función para ajustar la cantidad según las restricciones del tamaño de lote
def adjust_quantity(symbol, quantity):
    symbol_info = get_symbol_info(symbol)
    if symbol_info:
        # Obtener las restricciones del tamaño de lote
        lot_size_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'), None)
        if lot_size_filter:
            min_qty = float(lot_size_filter['minQty'])
            step_size = float(lot_size_filter['stepSize'])
            quantity = max(min_qty, quantity)
            quantity = round(quantity / step_size) * step_size  # Redondear a múltiplo de step_size
        return quantity
    return None

def place_order_with_risk_management(symbol, quantity, side, stop_loss, take_profit, order_type='MARKET'):
    try:
        # Ajustar la cantidad a la precisión correcta
        adjusted_quantity = adjust_quantity(symbol, quantity)

        order = client.create_order(
            symbol=symbol,
            side=side,
            type=order_type,
            quantity=adjusted_quantity
        )
        logging.info(f"Placed {side} order for {adjusted_quantity} {symbol} with Stop Loss: {stop_loss} and Take Profit: {take_profit}")
    except Exception as e:
        logging.error(f"Error placing order with risk management: {e}")
        

# Función principal del bot de trading
def run_trading_bot(symbol, interval, start_str, balance, stop_loss_percentage, take_profit_percentage, sleep_time):
    while True:
        try:
            logging.info("Fetching historical data...")
            data = get_historical_data(symbol, interval, start_str)
            if data.empty:
                logging.error("No data fetched, retrying...")
                time.sleep(sleep_time)
                continue

            logging.info("Applying trading strategy...")
            data = apply_strategy(data)

            current_price = data.iloc[-1]['close']
            stop_loss_price = current_price * (1 - stop_loss_percentage)
            take_profit_price = current_price * (1 + take_profit_percentage)

            logging.info("Current price: " + str(current_price))
            quantity = balance / current_price

            # Calculate total order cost if price is specified
            if current_price:
                total_cost = quantity * current_price
            else:
                total_cost = None

            # Get available balance of quote asset (e.g., USDT)
            quote_asset = 'USDT'
            available_balance = get_balance(quote_asset)

            # Check if there's enough balance for the order
            if total_cost and total_cost > available_balance:
                logging.info("Insufficient balance to place order. Available: " + str(available_balance))
            else:
                logging.info("Executing trades...")
                place_order_with_risk_management(symbol, quantity, 'BUY', stop_loss_price, take_profit_price)

                logging.info("Sleeping for the specified interval...")
            
            time.sleep(sleep_time)

        except Exception as e:
            logging.error(f"An error occurred: {e}")
            logging.info("Retrying after a short break...")
            time.sleep(sleep_time)

# Parámetros de la estrategia
symbol = 'BTCUSDT'
interval = Client.KLINE_INTERVAL_1HOUR
start_str = '1 month ago UTC'
balance = 65  # Balance inicial en USD
stop_loss_percentage = 0.05  # 5% debajo del precio de compra
take_profit_percentage = 0.10  # 10% por encima del precio de compra
sleep_time = 30  # Intervalo en segundos

# Iniciar el bot de trading
run_trading_bot(symbol, interval, start_str, balance, stop_loss_percentage, take_profit_percentage, sleep_time)
