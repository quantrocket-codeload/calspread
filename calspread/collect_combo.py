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
import io
from quantrocket.master import download_master_file, create_combo
from quantrocket.realtime import collect_market_data


def collect_combo(universe, contract_months, tick_db, until=None):
    """
    Creates a combo and initiates real-time data collection for it.

    Parameters
    ----------
    universe : str, required
        the universe of futures from which to select the contract contract_months

    contract_months : tuple, required
        a tuple of contract months which should make up the legs of the spread,
        for example, (1, 2) for the first and second closest months to expiration

    tick_db : str, required
        the tick db code for real-time data collection

    until : str, optional
        collect real-time data until this time (for example, '16:30:00 America/New_York')
    """

    # query non-expired futures contracts
    f = io.StringIO()
    download_master_file(f, universes=universe, fields="RolloverDate", exclude_expired=True)
    contracts = pd.read_csv(f, index_col="RolloverDate", parse_dates=["RolloverDate"])

    # sort by RolloverDate
    conids = contracts.ConId.sort_index().tolist()

    conid_1 = conids[contract_months[0] - 1]
    conid_2 = conids[contract_months[1] - 1]

    # Create the combo if it doesn't already exist
    result = create_combo([
        ["BUY", 1, conid_1],
        ["SELL", 1, conid_2]])

    combo_conid = result["conid"]

    # initiate data collection
    collect_market_data(tick_db, conids=combo_conid, until=until)
