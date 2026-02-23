#!/usr/bin/env python3
"""
Polymarket Position Redemption Script
Redeem winning positions directly from the blockchain
"""

import os
import sys
import json
from pathlib import Path

# Load environment
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from web3 import Web3

# Contract addresses
CONTRACTS = {
    "USDC_E": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
    "CTF": "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045",
}

POLYGON_CHAIN_ID = 137

# CTF Contract ABI with redeemPositions
CTF_ABI = [
    {
        "inputs": [
            {"name": "collateralToken", "type": "address"},
            {"name": "parentCollectionId", "type": "bytes32"},
            {"name": "conditionId", "type": "bytes32"},
            {"name": "indexSets", "type": "uint256[]"},
        ],
        "name": "redeemPositions",
        "outputs": [],
        "type": "function",
    },
    {
        "inputs": [
            {"name": "_owner", "type": "address"},
            {"name": "_id", "type": "uint256"},
        ],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    },
]

# Your winning positions
BTC_MARKET = {
    "market_id": "1369917",
    "condition_id": "0xf972542880343e9bb9fc75aec332b34d1becf0e0b8a7aee37b3c6f43f694ce7a",
    "yes_token_id": "45442090861283347285012595833377035239872952558521549204230188898220802803962",
    "no_token_id": "13782806396532337415223495923112396320408845236943005630162193384909857078881",
}

class PositionRedeemer:
    def __init__(self):
        # Load from skill directory .env
        import subprocess
        result = subprocess.run(
            "cd /root/.openclaw/skills/polyclaw && cat .env | grep POLYCLAW_PRIVATE_KEY",
            shell=True, capture_output=True, text=True
        )
        env_line = result.stdout.strip()
        if '=' in env_line:
            self.private_key = env_line.split('=', 1)[1].strip()
        else:
            raise ValueError("Private key not found in .env")
        
        # Load RPC from .env
        result = subprocess.run(
            "cd /root/.openclaw/skills/polyclaw && cat .env | grep CHAINSTACK_NODE",
            shell=True, capture_output=True, text=True
        )
        env_line = result.stdout.strip()
        if '=' in env_line:
            rpc_url = env_line.split('=', 1)[1].strip()
        else:
            raise ValueError("RPC URL not found")
        
        self.w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 60}))
        self.account = self.w3.eth.account.from_key(self.private_key)
        self.address = self.account.address
        
        self.ctf = self.w3.eth.contract(
            address=Web3.to_checksum_address(CONTRACTS["CTF"]),
            abi=CTF_ABI
        )
        
        print(f"Redeemer initialized")
        print(f"Address: {self.address}")
        print(f"Chain: Polygon (ID: {POLYGON_CHAIN_ID})")
    
    def get_token_balance(self, token_id: str) -> int:
        """Get balance of a specific position token"""
        try:
            balance = self.ctf.functions.balanceOf(
                self.address,
                int(token_id)
            ).call()
            return balance
        except Exception as e:
            print(f"Error checking balance: {e}")
            return 0
    
    def redeem_position(self, condition_id: str, index_sets: list) -> str:
        """Redeem a winning position"""
        try:
            # Convert condition_id to bytes32
            condition_bytes = bytes.fromhex(
                condition_id[2:] if condition_id.startswith("0x") else condition_id
            )
            
            # Build transaction
            tx = self.ctf.functions.redeemPositions(
                Web3.to_checksum_address(CONTRACTS["USDC_E"]),
                bytes(32),  # parentCollectionId (empty)
                condition_bytes,
                index_sets  # [1] for YES, [2] for NO
            ).build_transaction({
                "from": self.address,
                "nonce": self.w3.eth.get_transaction_count(self.address),
                "gas": 300000,
                "gasPrice": self.w3.eth.gas_price,
                "chainId": POLYGON_CHAIN_ID,
            })
            
            # Sign and send
            signed = self.account.sign_transaction(tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            
            print(f"Redeem TX submitted: {tx_hash.hex()}")
            
            # Wait for receipt
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            if receipt["status"] == 1:
                print(f"✅ Redeem successful! Block: {receipt['blockNumber']}")
                return tx_hash.hex()
            else:
                print("❌ Redeem failed")
                return None
                
        except Exception as e:
            print(f"❌ Redeem error: {e}")
            return None
    
    def check_and_redeem_btc_positions(self):
        """Check and redeem all BTC >$66K positions"""
        print("\n" + "="*60)
        print("CHECKING BTC >$66K POSITIONS")
        print("="*60)
        
        # Check YES token balance
        yes_token_id = BTC_MARKET["yes_token_id"]
        yes_balance = self.get_token_balance(yes_token_id)
        
        print(f"\nYES Token Balance: {yes_balance / 1e6:.2f} USDC.e")
        
        if yes_balance > 0:
            print(f"\n🎯 Found winning YES position!")
            print(f"Attempting to redeem...")
            
            # Redeem YES position (index set [1] = YES)
            tx_hash = self.redeem_position(
                BTC_MARKET["condition_id"],
                [1]  # YES = index 1
            )
            
            if tx_hash:
                print(f"\n✅ Redeemed successfully!")
                print(f"TX: {tx_hash}")
                print(f"Check: https://polygonscan.com/tx/{tx_hash}")
        else:
            print("\n⚠️  No YES tokens found to redeem")
            print("Either already redeemed or position doesn't exist")
    
    def get_usdc_balance(self) -> float:
        """Get current USDC.e balance"""
        try:
            # USDC.e ERC20 contract
            usdc_abi = [
                {
                    "constant": True,
                    "inputs": [{"name": "_owner", "type": "address"}],
                    "name": "balanceOf",
                    "outputs": [{"name": "", "type": "uint256"}],
                    "type": "function",
                }
            ]
            usdc = self.w3.eth.contract(
                address=Web3.to_checksum_address(CONTRACTS["USDC_E"]),
                abi=usdc_abi
            )
            balance = usdc.functions.balanceOf(self.address).call()
            return balance / 1e6
        except Exception as e:
            print(f"Error getting USDC balance: {e}")
            return 0

def main():
    print("="*60)
    print("POLYMARKET POSITION REDEMPTION TOOL")
    print("="*60)
    
    redeemer = PositionRedeemer()
    
    # Show current balance
    usdc_before = redeemer.get_usdc_balance()
    print(f"\nUSDC.e Balance Before: ${usdc_before:.2f}")
    
    # Check and redeem BTC positions
    redeemer.check_and_redeem_btc_positions()
    
    # Show new balance
    usdc_after = redeemer.get_usdc_balance()
    print(f"\nUSDC.e Balance After: ${usdc_after:.2f}")
    print(f"Change: ${usdc_after - usdc_before:+.2f}")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    main()
