import os
from ape import Contract
from typing import Union


class Vault:
    def __init__(self, address: str, sender: str):
        self.contract = Contract(
            address,
            # abi=os.path.join(os.path.dirname(__file__), "assets/vault.json"),
        )
        self.vault_proxy = Contract(
            self.contract.getAccessor(),
            # abi=os.path.join(os.path.dirname(__file__), "assets/vault_proxy.json"),
        )
        self.name = self.contract.name()
        self.symbol = self.contract.symbol()
        self.decimals = self.contract.decimals()
        self.denomination_asset = Contract(self.vault_proxy.getDenominationAsset())
        self.denomination_asset_decimals = self.denomination_asset.decimals()

        self.sender = sender

    def get_timelock(self) -> int:
        return self.vault_proxy.getSharesActionTimelock()
    
    def get_total_shares(self):
        return self.vault_proxy.totalSupply() / 10**self.decimals

    def deposit(self, amount: Union[int, float], slippage: float = 0.01, simulate: bool = False):
        scaled_amount = int((amount * 10**self.denomination_asset_decimals) * (1 - slippage))
        if scaled_amount < self.denomination_asset.allowance(_owner=self.sender, _spender=self.vault_proxy):
            self.denomination_asset.approve(self.vault_proxy, scaled_amount, sender=self.sender)
        if simulate:
            return self.vault_proxy.buyShares.call(scaled_amount, sender=self.sender)
        else:
            return self.vault_proxy.buyShares(scaled_amount, sender=self.sender)
        
    def redeem(self, shares_amount: int, payout_assets: list, payout_percentages: list, recipient: str=None, simulate: bool = False):
        """
        - payout_percentages is in bps
        - payout_assets - list of asset addresses
        """
        if recipient is None:
            recipient = self.sender

        # TODO: accept payout_percentages as q list of floats and parse the decimals here
        if simulate:
            return self.vault_proxy.redeemSharesForSpecificAssets.call(recipient, shares_amount, payout_assets, payout_percentages, sender=self.sender)
        else:
            return self.vault_proxy.redeemSharesForSpecificAssets(recipient, shares_amount, payout_assets, payout_percentages, sender=self.sender)

    
