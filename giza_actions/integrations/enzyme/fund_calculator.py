import os
from ape import Contract, chain
from typing import Union
from giza_actions.integrations.enzyme.constants import ADDRESSES


class FundCalculator:
    def __init__(self, chain_id: int=1):
        self.contract = Contract(
            ADDRESSES[chain_id]['fundValueCalculatorRouter'],
            abi=os.path.join(os.path.dirname(__file__), "assets/fund_value_calculator_router.json"),
        )
    
    def get_assets_value(self, vault_proxy: str, quote_asset: str = None, net: bool = False, block_number: int = None):
        if block_number is None:
            block_number = chain.blocks[-1].number

        if quote_asset is None:
            if net:
                return self.contract.calcNav.call(vault_proxy, block_identifier=block_number)
            else:
                return self.contract.calcGav.call(vault_proxy, block_identifier=block_number)
        else:
            if net:
                return self.contract.calcNavInAsset.call(vault_proxy, quote_asset, block_identifier=block_number)
            else:
                return self.contract.calcGavInAsset.call(vault_proxy, quote_asset, block_identifier=block_number)


    def get_share_value(self, vault_proxy: str, quote_asset: str = None, net: bool = False, shareholder: str = None, block_number: int = None):
        if block_number is None:
            block_number = chain.blocks[-1].number

        if quote_asset is None:
            if net:
                if shareholder is None:
                    return self.contract.calcNetShareValue.call(vault_proxy, block_identifier = block_number)
                else:
                    return self.contract.calcNetValueForSharesHolder.call(vault_proxy, shareholder, block_identifier = block_number)
            else:
                if shareholder is None:
                    return self.contract.calcGrossShareValue.call(vault_proxy, block_identifier = block_number)
                else:
                    return self.contract.calcGrossValueForSharesHolder.call(vault_proxy, shareholder, block_identifier = block_number)

        else:
            if net:
                if shareholder is None:
                    return self.contract.calcNetShareValueInAsset.call(vault_proxy, quote_asset, block_identifier = block_number)
                else:
                    return self.contract.calcNetValueForSharesHolderInAsset.call(vault_proxy, quote_asset, shareholder, block_identifier = block_number)
            else:
                if shareholder is None:
                    return self.contract.calcGrossShareValueInAsset.call(vault_proxy, quote_asset, block_identifier = block_number)
                else:
                    return self.contract.calcGrossValueForSharesHolderInAsset.call(vault_proxy, quote_asset, shareholder, block_identifier = block_number)
    