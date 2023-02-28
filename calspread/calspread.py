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


class CalendarSpreadStrategy(Moonshot):
    """
    Intraday pairs trading strategy for futures calendar spreads.
    """

    CODE = None
    DB = None
    DB_FIELDS = ["Close", "Open"]
    LOOKBACK_WINDOW = 0  # explicitly set LOOKBACK_WINDOW to 0 to avoid loading too much data
    BBAND_LOOKBACK_WINDOW = 60  # Compute Bollinger Bands over this period (number of minutes)
    BBAND_STD = 2  # Set Bollinger Bands this many standard deviations away from mean
    CONTRACT_NUMS = 1, 2  # the contract numbers from which to form the spread (1 = front month)
    FILL_AT_MIDPOINT = False # True to model getting filled at the midpoint, False to pay the spread

    def prices_to_signals(self, prices: pd.DataFrame):
        """
        Generates a DataFrame of signals indicating whether to long or short
        the spread.
        """
        # for BID_ASK bar type, Open contains the average bid and Close contains
        # the avg ask
        bids = prices.loc["Open"]
        asks = prices.loc["Close"]

        # Get a DataFrame of contract numbers and a Boolean mask of the
        # contract nums constituting the spread
        contract_nums = get_contract_nums_reindexed_like(bids, limit=max(self.CONTRACT_NUMS))
        are_month_a_contracts = contract_nums == self.CONTRACT_NUMS[0]
        are_month_b_contracts = contract_nums == self.CONTRACT_NUMS[1]

        # Get a Series of bids and asks for the respective contract months by
        # masking with contract num and taking the mean of each row (relying on
        # the fact that the mask leaves only one observation per row)
        month_a_bids = bids.where(are_month_a_contracts).mean(axis=1)
        month_a_asks = asks.where(are_month_a_contracts).mean(axis=1)

        month_b_bids = bids.where(are_month_b_contracts).mean(axis=1)
        month_b_asks = asks.where(are_month_b_contracts).mean(axis=1)

        # Buying the spread means buying the month A contract at the ask and
        # selling the month B contract at the bid
        spreads_for_buys = month_a_asks - month_b_bids
        means_for_buys = spreads_for_buys.fillna(method="ffill").rolling(self.BBAND_LOOKBACK_WINDOW).mean()
        stds_for_buys = spreads_for_buys.fillna(method="ffill").rolling(self.BBAND_LOOKBACK_WINDOW).std()
        upper_bands_for_buys = means_for_buys + self.BBAND_STD * stds_for_buys
        lower_bands_for_buys = means_for_buys - self.BBAND_STD * stds_for_buys

        # Selling the spread means selling the month A contract at the bid
        # and buying the month B contract at the ask
        spreads_for_sells = month_a_bids - month_b_asks
        means_for_sells = spreads_for_sells.fillna(method="ffill").rolling(self.BBAND_LOOKBACK_WINDOW).mean()
        stds_for_sells = spreads_for_sells.fillna(method="ffill").rolling(self.BBAND_LOOKBACK_WINDOW).std()
        upper_bands_for_sells = means_for_sells + self.BBAND_STD * stds_for_buys
        lower_bands_for_sells = means_for_sells - self.BBAND_STD * stds_for_buys

        # Long (short) the spread when it crosses below (above) the lower (upper)
        # band, then exit when it crosses the mean
        long_entries = spreads_for_buys < lower_bands_for_buys
        long_exits = spreads_for_buys >= means_for_buys
        short_entries = spreads_for_sells > upper_bands_for_sells
        short_exits = spreads_for_sells <= means_for_sells

        # Combine entries and exits
        ones = pd.Series(1, index=spreads_for_buys.index)
        zeros = pd.Series(0, index=spreads_for_buys.index)
        minus_ones = pd.Series(-1, index=spreads_for_buys.index)
        long_signals = ones.where(long_entries).fillna(zeros.where(long_exits)).fillna(method="ffill")
        short_signals = minus_ones.where(short_entries).fillna(zeros.where(short_exits)).fillna(method="ffill")
        signals = long_signals + short_signals

        # Broadcast Series to DataFrame
        signals = bids.apply(lambda x: signals)

        # Signal applies to month A contract, reverse signal applies to month
        # B contract
        signals = signals.where(are_month_a_contracts).fillna(
            -signals.where(are_month_b_contracts)).fillna(0)
        return signals

    def signals_to_target_weights(self, signals: pd.DataFrame, prices: pd.DataFrame):
        # allocate half of capital to each signal
        weights = signals / 2
        return weights

    def target_weights_to_positions(self, weights: pd.DataFrame, prices: pd.DataFrame):
        # Enter in the period after the signal
        positions = weights.shift()
        return positions

    def positions_to_gross_returns(self, positions: pd.DataFrame, prices: pd.DataFrame):
        bids = prices.loc["Open"]
        asks = prices.loc["Close"]
        midpoints = (bids + asks) / 2

        if self.FILL_AT_MIDPOINT:
            trade_prices = midpoints
        else:
            # We buy at the ask and sell at the bid
            are_buys = positions.diff() > 0
            are_sells = positions.diff() < 0

            trade_prices = asks.where(are_buys).fillna(
                bids.where(are_sells)).fillna(midpoints)

        gross_returns = trade_prices.pct_change() * positions.shift()
        return gross_returns


class CLCalendarSpreadStrategy(CalendarSpreadStrategy):

    CODE = "calspread-cl"
    UNIVERSES = "cl-fut"
    DB = "cl-1min-bbo"
    CONTRACT_NUMS = (1, 2)
    BBAND_LOOKBACK_WINDOW = 60
    BBAND_STD = 2
    COMMISSION_CLASS = NymexCommission


class FrictionlessCLCalendarSpreadStrategy(CLCalendarSpreadStrategy):

    CODE = "calspread-cl-frictionless"
    COMMISSION_CLASS = None
    FILL_AT_MIDPOINT = True
