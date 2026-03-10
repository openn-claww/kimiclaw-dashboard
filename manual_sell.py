#!/usr/bin/env python3
"""
manual_sell.py — Browser automation to sell tokens on Polymarket.com
When CLOB fails, this script logs into Polymarket UI and sells tokens.

Usage:
    python3 manual_sell.py --token-id <TOKEN_ID> --amount <AMOUNT>
    
Requirements:
    pip install playwright
    playwright install chromium
"""

import argparse
import asyncio
from playwright.async_api import async_playwright
import os

# Polymarket credentials (store securely)
# Option 1: Set env vars
# Option 2: Use private key to sign transactions directly

POLYMARKET_URL = "https://polymarket.com"


async def sell_tokens(token_id: str, amount: float, headless: bool = False):
    """
    Sell tokens on Polymarket using browser automation.
    
    Args:
        token_id: The token ID to sell (from position data)
        amount: Amount to sell
        headless: If False, shows browser window for debugging
    """
    
    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            # Go to Polymarket
            print(f"Opening {POLYMARKET_URL}...")
            await page.goto(POLYMARKET_URL)
            await page.wait_for_load_state('networkidle')
            
            # Check if already logged in (via wallet connection)
            # Polymarket uses MetaMask or other wallets
            print("Please connect your wallet manually if not connected")
            print("Waiting 30 seconds for wallet connection...")
            await asyncio.sleep(30)
            
            # Navigate to portfolio/positions
            print("Navigating to portfolio...")
            await page.goto(f"{POLYMARKET_URL}/portfolio")
            await page.wait_for_load_state('networkidle')
            
            # Find the position
            print(f"Looking for position with token {token_id}...")
            # This selector needs to be adjusted based on actual Polymarket UI
            position_selector = f"[data-token-id='{token_id}']"  # May need adjustment
            
            try:
                await page.wait_for_selector(position_selector, timeout=10000)
                print("Position found!")
            except:
                print("Position not found by token ID, looking manually...")
                # Take screenshot for debugging
                await page.screenshot(path='positions_page.png')
                print("Screenshot saved to positions_page.png")
            
            # Click Sell button
            sell_button = await page.query_selector("text=Sell")
            if sell_button:
                print("Clicking Sell button...")
                await sell_button.click()
                await asyncio.sleep(2)
            
            # Enter amount
            amount_input = await page.query_selector("input[placeholder*='amount' i], input[type='number']")
            if amount_input:
                print(f"Entering amount: {amount}")
                await amount_input.fill(str(amount))
                await asyncio.sleep(1)
            
            # Confirm sell
            confirm_button = await page.query_selector("text=Confirm, text=Sell Now, button:has-text('Sell')")
            if confirm_button:
                print("Clicking confirm...")
                await confirm_button.click()
                
                # Wait for transaction
                print("Waiting for transaction confirmation...")
                await asyncio.sleep(15)
                
                # Take screenshot of result
                await page.screenshot(path='sell_result.png')
                print("Screenshot saved to sell_result.png")
                print("✅ Sell order submitted!")
            else:
                print("❌ Could not find confirm button")
                
        except Exception as e:
            print(f"Error: {e}")
            await page.screenshot(path='error.png')
            print("Error screenshot saved to error.png")
            
        finally:
            await browser.close()


def main():
    parser = argparse.ArgumentParser(description='Sell Polymarket tokens manually')
    parser.add_argument('--token-id', required=True, help='Token ID to sell')
    parser.add_argument('--amount', type=float, required=True, help='Amount to sell')
    parser.add_argument('--headless', action='store_true', help='Run without browser window')
    parser.add_argument('--list', action='store_true', help='List open positions')
    
    args = parser.parse_args()
    
    if args.list:
        # Call PolyClaw to list positions
        import subprocess
        result = subprocess.run(
            ['uv', 'run', 'python', 'scripts/polyclaw.py', 'positions'],
            cwd='/root/.openclaw/skills/polyclaw',
            capture_output=True, text=True
        )
        print(result.stdout)
        return
    
    # Run the sell automation
    asyncio.run(sell_tokens(args.token_id, args.amount, headless=args.headless))


if __name__ == "__main__":
    main()
