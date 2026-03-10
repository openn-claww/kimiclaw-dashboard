"""
wallet_manager.py — Polygon wallet balance and approval management.

Handles:
  - USDC.e balance queries (Polygon)
  - POL (native gas) balance
  - ERC-20 approval checks and setting for Polymarket CTF Exchange
  - Safe balance formatting (6 decimals for USDC.e)
"""

import logging
from typing import Optional

from web3 import Web3
from web3.exceptions import ContractLogicError

from .exceptions import (
    InsufficientBalanceError,
    InsufficientGasError,
    ApprovalNotSetError,
    CLOBConnectionError,
)

logger = logging.getLogger(__name__)

# ── Polygon Mainnet Constants ────────────────────────────────────────────────
POLYGON_RPC = "https://polygon-rpc.com"

# USDC.e (bridged USDC on Polygon) — 6 decimals
USDC_E_ADDRESS = Web3.to_checksum_address("0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174")

# Polymarket CTF Exchange (needs USDC.e approval)
CTF_EXCHANGE_ADDRESS = Web3.to_checksum_address("0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E")

# Polymarket Neg Risk CTF Exchange
NEG_RISK_CTF_EXCHANGE = Web3.to_checksum_address("0xC5d563A36AE78145C45a50134d48A1215220f80a")

# Minimum POL required for gas (0.01 POL ≈ $0.005 at current prices)
MIN_POL_FOR_GAS = 0.01

# Minimum USDC.e to consider wallet "funded"
MIN_USDC_BALANCE = 1.0

# Minimal ERC-20 ABI for balance + allowance
ERC20_ABI = [
    {
        "name": "balanceOf",
        "type": "function",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
    },
    {
        "name": "allowance",
        "type": "function",
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"},
        ],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
    },
    {
        "name": "approve",
        "type": "function",
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
    },
    {
        "name": "decimals",
        "type": "function",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint8"}],
        "stateMutability": "view",
    },
]

MAX_UINT256 = 2**256 - 1


class WalletManager:
    """
    Manages Polygon wallet state for Polymarket live trading.

    Usage:
        wm = WalletManager(address="0xYOUR_ADDRESS", rpc_url=POLYGON_RPC)
        balances = wm.get_balances()
        wm.validate_for_trade(amount_usd=10.0)
    """

    def __init__(
        self,
        address: str,
        rpc_url: str = POLYGON_RPC,
        w3: Optional[Web3] = None,
    ):
        self.address = Web3.to_checksum_address(address)
        self.rpc_url = rpc_url

        if w3 is not None:
            self.w3 = w3
        else:
            self.w3 = Web3(Web3.HTTPProvider(rpc_url))
            if not self.w3.is_connected():
                raise CLOBConnectionError(rpc_url, "Web3 cannot connect to Polygon RPC")

        self._usdc = self.w3.eth.contract(
            address=USDC_E_ADDRESS, abi=ERC20_ABI
        )
        logger.info(f"WalletManager initialized for {self.address}")

    # ── Balance Queries ──────────────────────────────────────────────────────

    def get_usdc_balance(self) -> float:
        """Return USDC.e balance as a float (human-readable, 6 decimals)."""
        raw = self._usdc.functions.balanceOf(self.address).call()
        balance = raw / 1_000_000  # USDC.e has 6 decimals
        logger.debug(f"USDC.e balance: ${balance:.6f}")
        return balance

    def get_pol_balance(self) -> float:
        """Return native POL (MATIC) balance in POL units."""
        raw = self.w3.eth.get_balance(self.address)
        balance = self.w3.from_wei(raw, "ether")
        logger.debug(f"POL balance: {balance:.6f} POL")
        return float(balance)

    def get_balances(self) -> dict:
        """
        Return full wallet state dict.

        Returns:
            {
                'usdc_balance': float,      # USDC.e available
                'pol_balance': float,       # POL for gas
                'ctf_approved': bool,       # CTF Exchange approved
                'neg_risk_approved': bool,  # Neg Risk CTF approved
                'address': str,
                'sufficient_gas': bool,
                'ready_to_trade': bool,
            }
        """
        usdc = self.get_usdc_balance()
        pol = self.get_pol_balance()
        ctf_approved = self.check_approval(CTF_EXCHANGE_ADDRESS)
        neg_risk_approved = self.check_approval(NEG_RISK_CTF_EXCHANGE)

        sufficient_gas = pol >= MIN_POL_FOR_GAS
        ready = usdc >= MIN_USDC_BALANCE and sufficient_gas and ctf_approved

        state = {
            "usdc_balance": usdc,
            "pol_balance": pol,
            "ctf_approved": ctf_approved,
            "neg_risk_approved": neg_risk_approved,
            "address": self.address,
            "sufficient_gas": sufficient_gas,
            "ready_to_trade": ready,
        }

        logger.info(
            f"Wallet state — USDC: ${usdc:.2f} | POL: {pol:.4f} | "
            f"CTF approved: {ctf_approved} | Ready: {ready}"
        )
        return state

    # ── Approval Checks ──────────────────────────────────────────────────────

    def check_approval(self, spender: str) -> bool:
        """
        Check if USDC.e is approved for the given spender.
        Returns True if allowance > 0 (any amount approved).
        """
        spender = Web3.to_checksum_address(spender)
        allowance = self._usdc.functions.allowance(self.address, spender).call()
        approved = allowance > 0
        logger.debug(f"Approval for {spender}: {allowance} raw ({approved})")
        return approved

    def ensure_approvals(self, private_key: str) -> dict:
        """
        Set max USDC.e approval for CTF Exchange and Neg Risk CTF Exchange
        if not already approved.

        ⚠️  This sends on-chain transactions — requires POL for gas.

        Args:
            private_key: Wallet private key (hex string, with or without 0x)

        Returns:
            {
                'ctf_tx': str or None,       # tx hash if approval sent
                'neg_risk_tx': str or None,
                'already_approved': bool,
            }
        """
        if not private_key.startswith("0x"):
            private_key = "0x" + private_key

        pol = self.get_pol_balance()
        if pol < MIN_POL_FOR_GAS:
            raise InsufficientGasError(pol)

        results = {"ctf_tx": None, "neg_risk_tx": None, "already_approved": False}
        already_count = 0

        for name, spender in [
            ("CTF Exchange", CTF_EXCHANGE_ADDRESS),
            ("Neg Risk CTF", NEG_RISK_CTF_EXCHANGE),
        ]:
            if self.check_approval(spender):
                logger.info(f"{name} already approved — skipping")
                already_count += 1
                continue

            logger.info(f"Setting max approval for {name} ({spender})...")
            tx_hash = self._send_approve_tx(private_key, spender)

            if name == "CTF Exchange":
                results["ctf_tx"] = tx_hash
            else:
                results["neg_risk_tx"] = tx_hash

            logger.info(f"{name} approval tx sent: {tx_hash}")

        results["already_approved"] = already_count == 2
        return results

    def _send_approve_tx(self, private_key: str, spender: str) -> str:
        """Build, sign, and send an ERC-20 approve(MAX_UINT256) tx. Returns tx hash."""
        nonce = self.w3.eth.get_transaction_count(self.address)
        gas_price = self.w3.eth.gas_price

        tx = self._usdc.functions.approve(spender, MAX_UINT256).build_transaction({
            "from": self.address,
            "nonce": nonce,
            "gasPrice": gas_price,
            "gas": 100_000,
        })

        signed = self.w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        if receipt.status != 1:
            raise ContractLogicError(f"Approval transaction failed: {tx_hash.hex()}")

        return tx_hash.hex()

    # ── Trade Validation ─────────────────────────────────────────────────────

    def validate_for_trade(self, amount_usd: float) -> None:
        """
        Validate wallet is ready to execute a trade of `amount_usd`.

        Raises:
            InsufficientBalanceError: if USDC balance < amount_usd
            InsufficientGasError: if POL balance < MIN_POL_FOR_GAS
            ApprovalNotSetError: if USDC not approved for CTF Exchange
        """
        usdc = self.get_usdc_balance()
        if usdc < amount_usd:
            raise InsufficientBalanceError(required=amount_usd, available=usdc)

        pol = self.get_pol_balance()
        if pol < MIN_POL_FOR_GAS:
            raise InsufficientGasError(pol)

        if not self.check_approval(CTF_EXCHANGE_ADDRESS):
            raise ApprovalNotSetError()

        logger.info(
            f"Wallet validated for ${amount_usd:.2f} trade — "
            f"USDC: ${usdc:.2f}, POL: {pol:.4f}"
        )

    def get_available_capital(self, reserve_pct: float = 0.05) -> float:
        """
        Return available trading capital after reserving a buffer.

        Args:
            reserve_pct: fraction to hold back (default 5%)

        Returns:
            float: USDC available for trading
        """
        usdc = self.get_usdc_balance()
        available = usdc * (1 - reserve_pct)
        logger.info(f"Available capital: ${available:.2f} (${usdc:.2f} * {1-reserve_pct:.0%})")
        return available
