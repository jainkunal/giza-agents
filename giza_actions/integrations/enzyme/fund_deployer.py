import os
from ape import Contract, chain
from giza_actions.integrations.enzyme.constants import ADDRESSES
import re
from typing import List

class FundDeployer:
    def __init__(self, sender: str, chain_id: int = 1):
        self.contract = Contract(
            ADDRESSES[chain_id]['fundDeployer'],
            abi=os.path.join(os.path.dirname(__file__), "assets/fund_deployer.json"),
        )
        self.sender = sender

    def create_fund(self, name: str, symbol: str, denomination_asset: str, shares_action_timelock_in_seconds: int, fee_manager_config_data: hex, policy_manager_config_data: hex, fund_owner: str) -> str:
        return self.contract.createNewFund(fund_owner, name, symbol, denomination_asset, shares_action_timelock_in_seconds, fee_manager_config_data, policy_manager_config_data, sender=self.sender)

    def get_vaults_list(self, start_block: int = 0, end_block: int = 0):
        start_block = 0
        if end_block == 0:
            end_block = chain.blocks[-1].number
        try:
            vaults_created = self.contract.NewFundCreated.query("*", start_block=start_block, stop_block=end_block, engine_to_use="subsquid")
        except Exception as e:
            try:
                last_integer = re.findall(r'\d+', e)[-1]  # Extracts all integers and picks the last one
                end_block = int(last_integer)
                vaults_created = self.contract.NewFundCreated.query("*", start_block=start_block, stop_block=end_block, engine_to_use="subsquid")
            except:
                vaults_created = self.contract.NewFundCreated.query("*", start_block=start_block, stop_block=end_block) 
        
        return vaults_created['event_arguments'].values
