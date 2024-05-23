import os
from giza_actions.integrations.enzyme.fund_deployer import FundDeployer
from giza_actions.integrations.enzyme.fund_calculator import FundCalculator

class Enzyme:
    def __init__(self, sender: str, chain_id: int = 1):
        self.chain_id = chain_id
        self.fund_deployer = FundDeployer(sender, self.chain_id)
        self.fund_calculator = FundCalculator(self.chain_id)
        self.sender = sender

    def create_fund(self, name: str, symbol: str, denomination_asset: str, shares_action_timelock_in_seconds: int, fee_manager_config_data: hex, policy_manager_config_data: hex, fund_owner: str = None) -> str:
        if fund_owner is None:
            fund_owner = self.sender
        return self.fund_deployer.create_fund(name=name, symbol=symbol, denomination_asset=denomination_asset, shares_action_timelock_in_seconds=shares_action_timelock_in_seconds, fee_manager_config_data=fee_manager_config_data, policy_manager_config_data=policy_manager_config_data, fund_owner=fund_owner)

    def get_vaults_list(self, start_block: int = 0, end_block: int = 0):
        return self.fund_deployer.get_vaults_list(start_block=start_block, end_block=end_block)
    
    def get_vault_assets_value(self, vault_proxy: str, quote_asset: str = None, net: bool = False, block_number: int = None):
        return self.fund_calculator.get_assets_value(vault_proxy=vault_proxy, quote_asset=quote_asset, net=net, block_number=block_number)
    
    def get_vault_share_value(self, vault_proxy: str, quote_asset: str = None, net: bool = False, shareholder: str = None, block_number: int = None):
        return self.fund_calculator.get_share_value(vault_proxy=vault_proxy, quote_asset=quote_asset, net=net, shareholder=shareholder, block_number=block_number)

    