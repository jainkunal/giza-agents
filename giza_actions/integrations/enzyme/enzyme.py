import os
from giza_actions.integrations.enzyme.fund_deployer import FundDeployer

class Enzyme:
    def __init__(self, address: str, sender: str):
        self.fund_deployer = FundDeployer(address, sender)
        self.sender = sender

    def create_vault(self, name: str, symbol: str, denomination_asset: str, shares_action_timelock_in_seconds: int, fee_manager_config_data: hex, policy_manager_config_data: hex, owner: str = None) -> str:
        if owner is None:
            owner = self.sender
        return self.fund_deployer.create_vault(_fundOwner=owner, _fundName=name, _fundSymbol=symbol, _denominationAsset=denomination_asset, _sharesActionTimelock=shares_action_timelock_in_seconds, _feeManagerConfigData=fee_manager_config_data, _policyManagerConfigData=policy_manager_config_data, sender=self.sender)

    def get_vaults_list(self):
        return self.fund_deployer.get_vaults_list()

    