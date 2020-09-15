import grequests
import json
import sys

import argparse

from functools import lru_cache
from typing import List, Dict, Callable, Tuple

from queue import PriorityQueue
from dataclasses import dataclass
from enum import Enum


URL_struct = Tuple[str, str]

class Order():
    def __init__(self, price, quantity, _, exchange):
        self.price: float = float(price)
        self.quantity: float = float(quantity)

        self.exchange: int = exchange

    # implement comporators for Priority Queue selection
    def __eq__(self, other):
        return self.price == other.price

    def __ge__(self, other):
        return not self.price < other.price

    def __gt__(self, other):
        return self.price > other.price

    def __le__(self, other):
        return not other.price < self.price

    def __lt__(self, other):
        return self.price == other.price

    def __ne__(self, other):
        return self.price != other.price

    def __str__(self):
        return f"Order({self.price}, {self.quantity}, {self.exchange.name})"

    def __repr__(self):
        return f"Order(price: {self.price}, quantity: {self.quantity}, exchange: {self.exchange.name})\n"



class OrderBook():
    def __init__(self, lowestFirst = True):
        self._bids = PriorityQueue()
        self._asks = PriorityQueue()

    def bid_size(self):
        return self._bids.qsize()

    def ask_size(self):
        return self._asks.qsize()

    def put_bid(self, order):
        self._bids.put((-order.price, order))

        # queue has been updated so don't use cache for show
        self.show_bids.cache_clear()

    def put_ask(self, order):
        self._asks.put((order.price, order))

        # queue has been updated so don't use cache for show
        self.show_asks.cache_clear()

    def get_bid(self):
        _ , order = self._bids.get()
        return order

    def get_ask(self):
        _ , order = self._asks.get()
        return order

    @lru_cache
    def show_bids(self):
        return [order for _, order in self._bids.queue]

    @lru_cache
    def show_asks(self):
        return [order for _, order in self._asks.queue]

    @staticmethod
    def greedy_comp(order_list, capacity: float, delta: float):
        """Accumulate orders as long as we stay within the capacity buffer"""

        quantities = [order.quantity for order in order_list]
        prices = [order.price for order in order_list]

        order_count: int = len(order_list)
        selection = [0] * order_count

        total_coins = total_price = 0
        idx = 0

        while total_coins < capacity and idx < order_count:
            if (n := quantities[idx] + total_coins) < capacity * (1 + delta):
                total_coins = n
                total_price += quantities[idx] * prices[idx]
                selection[idx] = 1
                if total_coins >= capacity:
                    break
            idx += 1

        return total_coins, total_price, OrderBook.get_order_selection(order_list, selection)

    def greedy_sell(self, capacity):
        orders: list = self.show_bids()
        # Allow for 1% buffer from capacity; must be less than selling capacity
        return OrderBook.greedy_comp(orders, capacity, -.01)

    def greedy_buy(self, capacity):
        orders: list = self.show_asks()
        # Allow for 1% buffer from 10, must be more than buying capacity if possible
        return OrderBook.greedy_comp(orders, capacity, .01)

    @staticmethod
    def get_order_selection(order_book, selection):
        return [order_book[i] for i in range(len(selection)) if selection[i]]

    @staticmethod
    def optimum_comp(order_list, capacity, opt):
        """ Try to get as close to the capacity as possible while optimizing
            for price. Optimize is contingent on optimizing function (@param: opt)

            note: uses the knapsack algorithm under the hood
        """
        order_count = len(order_list)

        quantities = [order.quantity for order in reversed(order_list)]
        prices = [order.price for order in reversed(order_list)]

        best_value = 0
        selection = [0] * order_count

        @lru_cache(256)
        def _knapsack(capacity, i):
            if capacity == 0 or i == 0:
                best = 0

            elif quantities[i - 1] > capacity:
                best = _knapsack(capacity, i - 1)

            else:
                best = opt(_knapsack(capacity - quantities[i - 1], i - 1) + prices[i - 1],
                           _knapsack(capacity, i - 1))
            return best

        _knapsack.cache_clear()

        remainder = capacity
        for i in reversed(range(order_count)):
            selection[i] = int(_knapsack(remainder, i + 1) != _knapsack(remainder, i))

            remainder -= quantities[i] * selection[i]
            best_value += quantities[i] * prices[i] * selection[i]

        return best_value, capacity - remainder, OrderBook.get_order_selection(order_list, selection)

    def optimal_sell(order_book, capacity):
        orders: list = order_book.show_bids()
        # max is a function reference
        return OrderBook.optimum_comp(orders, capacity, max)

    def optimal_buy(order_book, capacity):
        orders: list = order_book.show_asks()
        # min is a function reference
        return OrderBook.optimum_comp(orders, capacity, min)


@dataclass
class ExchangeEnum(Enum):
    CoinBase = 1
    Gemini = 2
    Kraken = 3

class Exchange():
    def __init__(self, response, exchange_market):
        #@ TODO: Can optimize by not calling constructor on ALL bids
        # better error messaging could be used here
        self._bids: list = [Order(*bid, exchange_market)
                            for bid in response.get("bids", [])]

        self._asks: list = [Order(*ask, exchange_market)
                            for ask in response.get("asks", [])]

    @property
    def bids(self) -> list:
        return self._bids

    @property
    def asks(self) -> list:
        return self._asks

    def create_book(self):
        return OrderBook()


class CoinBase(Exchange):
    def __init__(self, response):
        Exchange.__init__(self, response, ExchangeEnum.CoinBase)

class Kraken(Exchange):
    def _no_errors(self, response) -> bool:
        if "error" in response:
            if response["error"]:
                raise Exception("Kraken Error")
        if "result" not in response:
            raise KeyError("Missing \"result\" key in Kraken JSON Response")

        if "XXBTZUSD" not in response["result"]:
            raise KeyError("Missing \"XXBTZUSD\" key in Kraken JSON Response")

    def __init__(self, response) -> None:
        # JSON API response may change keys at some later point
        self._no_errors(response)
        Exchange.__init__(self, response["result"]["XXBTZUSD"], ExchangeEnum.Kraken)

class Gemini(Exchange):
    def __init__(self, response: dict) -> None:
        def format_order(order_map):
            return Order(*order_map.values(), ExchangeEnum.Gemini)

        self._bids = [format_order(bid_map)
                      for bid_map in response.get("bids", {})]

        self._asks = [format_order(ask_map)
                      for ask_map in response.get("asks", {})]

def _format_map_to_url(exchange_map) -> URL_struct:
    # .values()[0] is a map with all the info for the exchange's endpoint
    # To support various coin endpoints we shouldn't use this approach
    exchange = list(exchange_map.values())[0]

    if "name" not in exchange:
        raise KeyError('JSON Exchange missing \"name\"')

    if "url" not in exchange:
        raise KeyError('JSON Exchange missing \"url\"')

    if "endpoint" not in exchange:
        raise KeyError('JSON Exchange missing \"endpoint\"')

    if "params" not in exchange:
        raise KeyError('JSON Exchange missing \"params\"')

    return (exchange["name"], exchange["url"] + exchange["endpoint"]
                              + exchange["params"])

def _format_json_to_urls(exchange_json) -> List[URL_struct]:
    if "exchanges" not in exchange_json:
        raise KeyError('JSON missing \"exchange\"')

    exchanges = exchange_json["exchanges"]
    return [_format_map_to_url(exchange_map) for exchange_map in exchanges]

def _exception_handler(response, exception):
    print(f"{type(exception).__name__} from {response.url}")
    return exception

def _run(name: str, master_book: OrderBook) -> Callable:
    if name not in SUPPORTED_EXCHANGES:
        raise KeyError(f"ERROR: {name} is not a supported exchange")

    exchange_object_ref: Callable = SUPPORTED_EXCHANGES[name]

    def run_func(response, *args, **kwargs):
        """Put all bids and asks into Master Book"""
        # Check response for errors
        response.raise_for_status()

        exchange = exchange_object_ref(response.json())

        bid: Order
        for bid in exchange.bids:
            master_book.put_bid(bid)

        ask: Order
        for ask in exchange.asks:
            master_book.put_ask(ask)

    return run_func

def main(desired_amount: float, file_name: str, optimize: bool) -> None:
    # generate master book - will hold all exchanges' orders
    master_book: OrderBook = OrderBook()

    url_tuples: List[URL_struct]
    with open(file_name) as fd:
        url_tuples = _format_json_to_urls(json.load(fd))

    # use grequests for async requests
    pool = [grequests.get(url, hooks = {"response" : _run(name, master_book)},
                               timeout = 2)
           for name, url in url_tuples]

    grequests.map(pool, exception_handler = _exception_handler)

    result_sell: Tuple[float, float, List[OrderBook]]
    result_buy: Tuple[float, float, List[OrderBook]]
    if optimize:
        result_sell = master_book.optimal_sell(desired_amount)
        result_buy = master_book.optimal_buy(desired_amount)
    else:
        result_sell = master_book.greedy_sell(desired_amount)
        result_buy = master_book.greedy_buy(desired_amount)

    print("*" * 35 + " IF YOU SELL " + "*" * 35)
    print(f" Quantity:\n\t{result_sell[0]}\n Total Price:\n\t{result_sell[1]}\n Selection:\n\t{result_sell[2]}")

    print("*" * 35 + " IF YOU BUY " + "*" * 35)
    print(f" Quantity:\n\t{result_buy[0]}\n Total Price:\n\t{result_buy[1]}\n Selection:\n\t{result_buy[2]}")

    # return (result_sell, result_buy)

def parse_flags():
    parser = argparse.ArgumentParser(description='Process quantities')
    parser.add_argument('-q',
                        action ='store',
                        default = 10,
                        help = 'Define a purchasing quantity (int) \nex: \-q \'10\'')

    parser.add_argument('-f',
                        action = 'store',
                        default = 'exchanges.json',
                        help = 'Add a json to extract exchanges (str) \nex:'
                               '\-f \'exchanges.json\'')

    parser.add_argument('-o',
                        action = 'store_true',
                        default = False,
                        help = 'Set flag to choose optimal buy')

    args = parser.parse_args()

    return float(args.q), args.f, args.o

if __name__ == "__main__":

    print(f"Running on {sys.version}\n\n")

    # Might be more scalable to have it in persistent storage
    SUPPORTED_EXCHANGES = {"CoinBase": CoinBase,
                           "Gemini": Gemini,
                           "Kraken": Kraken}
    args = parse_flags()

    main(*args)
