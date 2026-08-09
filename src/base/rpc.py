from web3 import Web3

class BaseRPCClient:
    def __init__(self, rpc_url: str):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not self.w3.is_connected():
            raise ConnectionError(f"Cannot connect to {rpc_url}")
    
    def get_balance(self, address: str) -> float:
        balance_wei = self.w3.eth.get_balance(Web3.to_checksum_address(address))
        return Web3.from_wei(balance_wei, 'ether')
    
    def is_contract(self, address: str) -> bool:
        code = self.w3.eth.get_code(Web3.to_checksum_address(address))
        return code != b''
    
    def get_latest_block(self) -> int:
        return self.w3.eth.block_number
