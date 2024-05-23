import os

from ape import Contract, accounts, networks, chain
from dotenv import find_dotenv, load_dotenv
import logging

from giza_actions.integrations.enzyme.enzyme import Enzyme
from giza_actions.integrations.enzyme.vault import Vault

load_dotenv(find_dotenv())
dev_passphrase = os.environ.get("DEV_PASSPHRASE")

logger = logging.getLogger(__name__)

with networks.parse_network_choice(f"ethereum:mainnet-fork:foundry"):
    sender = accounts.load("dev")
    sender.balance += int(2e18)
    sender.set_autosign(True, passphrase=dev_passphrase)
    enzyme = Enzyme(sender=sender)
    weth = Contract("WETH")
    new_vault = enzyme.create_fund(name="My Vault", symbol="MV", denomination_asset=weth.address, shares_action_timelock_in_seconds=100, fee_manager_config_data="0x", policy_manager_config_data="0x")
    curr_block = chain.blocks[-1].number
    # vaults_data = enzyme.get_vaults_list(start_block=curr_block - 1000, end_block=curr_block)
    # other_vault_data = vaults_data[0]
    other_vault_data = {'creator': '0x0D947D68f583e8B23ff816df9ff3f23a8Cfd7496', 'vaultProxy': '0x278C647F7cfb9D55580c69d3676938608C945ba8', 'comptrollerProxy': '0x746de9838BB3D14f1aC1b78Bd855E48201F221a6'}
    vault = Vault(proxy_address = other_vault_data['vaultProxy'], comptroller_address = other_vault_data['comptrollerProxy'], sender=sender)
    print(
        f"""
        Name: {vault.name}
        Symbol: {vault.symbol}
        Denomination Asset: {vault.denomination_asset}
        Shares Action Timelock: {vault.get_timelock()}
        Total shares: {vault.get_total_shares()}
        """
    )
    # Gross Asset Value in denomination asset
    gav = enzyme.get_vault_assets_value(vault.vault_proxy.address)['gav_']
    # Gross Asset Value in USDC 
    usdc = Contract("USDC")
    gav_usdc = enzyme.get_vault_assets_value(vault.vault_proxy.address, quote_asset=usdc.address)
    # Net Asset Value in denomination asset
    nav = enzyme.get_vault_assets_value(vault.vault_proxy.address, net=True)['nav_']
    # Net Asset Value in USDC 
    nav_usdc = enzyme.get_vault_assets_value(vault.vault_proxy.address, quote_asset=usdc.address, net=True)
    print(
        f"""
        Vault stats:
        GAV: {gav}
        GAV in USDC: {gav_usdc}
        NAV: {nav}
        NAV in USDC: {nav_usdc}
        """
    )

