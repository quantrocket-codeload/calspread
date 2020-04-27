# Copyright 2019 QuantRocket LLC - All Rights Reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pandas as pd
from moonshot import Moonshot
from moonshot.commission import FuturesCommission
from quantrocket.master import get_contract_nums_reindexed_like


class NymexCommission(FuturesCommission):
    BROKER_COMMISSION_PER_CONTRACT = 0.85
    EXCHANGE_FEE_PER_CONTRACT = 1.50 + 0.02
    CARRYING_FEE_PER_CONTRACT = 0  # Depends on equity in excess of margin requirement


class NativeCalendarSpreadStrategy(Moonshot):
    """
    Intraday pairs trading strategy for native futures calendar spreads.
    """

    CODE = None
    DB = None
    DB_FIELDS = ["BidPriceClose", "AskPriceClose"]
    LOOKBACK_WINDOW = 0  # explicitly set LOOKBACK_WINDOW to 0 to avoid loading too much data
    BBAND_LOOKBACK_WINDOW = 60  # Compute Bollinger Bands over this period (number of minutes)
    BBAND_STD = 2  # Set Bollinger Bands this many standard deviations away from mean

    def prices_to_signals(self, prices):
        """
        Generates a DataFrame of signals indicating whether to long or short
        the spread.
        """
        bids = prices.loc["BidPriceClose"].fillna(method="ffill")
        asks = prices.loc["AskPriceClose"].fillna(method="ffill")
        midpoints = (bids + asks) / 2

        means = midpoints.rolling(self.BBAND_LOOKBACK_WINDOW).mean()
        stds = midpoints.rolling(self.BBAND_LOOKBACK_WINDOW).std()
        upper_bands = means + self.BBAND_STD * stds
        lower_bands = means - self.BBAND_STD * stds

        # Long (short) the spread when it crosses below (above) the lower (upper)
        # band, then exit when it crosses the mean
        long_entries = asks < lower_bands
        long_exits = asks >= means
        short_entries = bids > upper_bands
        short_exits = bids <= means

        # Combine entries and exits
        ones = pd.DataFrame(1, index=midpoints.index, columns=midpoints.columns)
        zeros = pd.DataFrame(0, index=midpoints.index, columns=midpoints.columns)
        minus_ones = pd.DataFrame(-1, index=midpoints.index, columns=midpoints.columns)
        long_signals = ones.where(long_entries).fillna(
            zeros.where(long_exits)).fillna(method="ffill")
        short_signals = minus_ones.where(short_entries).fillna(zeros.where(short_exits)).fillna(method="ffill")
        signals = long_signals + short_signals

        return signals

    def signals_to_target_weights(self, signals, prices):
        """
        Convert signals to weights.

        We want to specify exact quantities but Moonshot assumes percentage weights. So,
        set the percentage weights very high, then we will reduce them to the exact quantities
        in limit_position_sizes.
        """
        weights = signals * 1000
        return weights

    def limit_position_sizes(self, prices):
        """
        Limit the position sizes to 1 spread contract.

        (Note that limit_position_sizes only cares about absolute values so no need
        to worry about signs.)
        """
        bids = prices.loc["BidPriceClose"]
        ones = pd.DataFrame(1, index=bids.index, columns=bids.columns)
        max_quantities_for_longs = max_quantities_for_shorts = ones
        return max_quantities_for_longs, max_quantities_for_shorts

    def target_weights_to_positions(self, weights, prices):
        # Enter in the period after the signal
        positions = weights.shift()
        return positions

    def positions_to_gross_returns(self, positions, prices):
        bids = prices.loc["BidPriceClose"]
        asks = prices.loc["AskPriceClose"]

        # We buy at the ask and sell at the bid
        are_buys = positions.diff() > 0
        are_sells = positions.diff() < 0
        midpoints = (bids + asks) / 2
        trade_prices = asks.where(are_buys).fillna(
            bids.where(are_sells)).fillna(midpoints)

        gross_returns = trade_prices.pct_change() * positions.shift()
        return gross_returns

    def order_stubs_to_orders(self, orders, prices):
        orders["Exchange"] = "NYMEX"
        orders["OrderType"] = "MKT"
        orders["Tif"] = "DAY"
        return orders


class CLNativeCalendarSpreadStrategy(NativeCalendarSpreadStrategy):

    CODE = "calspread-native-cl"
    DB = "cl-combo-tick-1min"
    CONTRACT_NUMS = (1, 2)
    BBAND_LOOKBACK_WINDOW = 60
    BBAND_STD = 2
    COMMISSION_CLASS = NymexCommission
    TIMEZONE = "America/New_York"
