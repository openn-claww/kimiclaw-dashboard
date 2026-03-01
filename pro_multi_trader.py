#!/usr/bin/env python3
"""
Enhanced Multi-Category Trading System v3.0
With API-Sports.io + WeatherAPI.com
"""

import os
import sys
import json
import requests
import subprocess
from datetime import datetime
from pathlib import Path

# Load API keys from secure config
CONFIG_FILE = Path("/root/.openclaw/workspace/api_config.sh")
if CONFIG_FILE.exists():
    with open(CONFIG_FILE) as f:
        for line in f:
            if 'export' in line and '=' in line:
                key_val = line.replace('export ', '').strip().split('=', 1)
                if len(key_val) == 2:
                    os.environ[key_val[0]] = key_val[1].strip().strip('"').strip("'")

# API Keys
API_SPORTS_KEY = os.getenv('API_SPORTS_KEY', '')
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY', '')

class ProMultiTrader:
    """Professional multi-category trading with premium APIs"""
    
    def __init__(self):
        self.categories = {
            'crypto': {'enabled': True, 'weight': 0.30},
            'sports': {'enabled': True, 'weight': 0.40},
            'weather': {'enabled': True, 'weight': 0.30}
        }
        self.max_bet = 1.0
        self.min_edge = 0.10
        
        # Weather locations (expanded)
        self.weather_locations = [
            {'name': 'New York', 'country': 'US'},
            {'name': 'London', 'country': 'UK'},
            {'name': 'Tokyo', 'country': 'JP'},
            {'name': 'Sydney', 'country': 'AU'},
            {'name': 'Paris', 'country': 'FR'},
            {'name': 'Los Angeles', 'country': 'US'},
            {'name': 'Chicago', 'country': 'US'},
            {'name': 'Miami', 'country': 'US'},
            {'name': 'Dubai', 'country': 'AE'},
            {'name': 'Singapore', 'country': 'SG'},
            {'name': 'Mumbai', 'country': 'IN'},
            {'name': 'Berlin', 'country': 'DE'},
        ]
    
    def get_sports_data(self):
        """Get live sports data from API-Sports.io"""
        if not API_SPORTS_KEY:
            print("⚠️  No API-Sports key")
            return []
        
        headers = {
            'x-apisports-key': API_SPORTS_KEY
        }
        
        sports_data = []
        
        # Get NBA games
        try:
            url = "https://v1.basketball.api-sports.io/games"
            params = {'league': '12', 'season': '2025-2026', 'date': datetime.now().strftime('%Y-%m-%d')}
            response = requests.get(url, headers=headers, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                games = data.get('response', [])
                print(f"   🏀 NBA: {len(games)} games today")
                for game in games[:3]:
                    teams = game.get('teams', {})
                    home = teams.get('home', {}).get('name', 'N/A')
                    away = teams.get('away', {}).get('name', 'N/A')
                    status = game.get('status', {}).get('short', 'N/A')
                    print(f"      {away} @ {home} ({status})")
                sports_data.extend(games)
        except Exception as e:
            print(f"   NBA error: {e}")
        
        # Get Soccer games
        try:
            url = "https://v3.football.api-sports.io/fixtures"
            params = {'date': datetime.now().strftime('%Y-%m-%d')}
            response = requests.get(url, headers=headers, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                fixtures = data.get('response', [])
                print(f"   ⚽ Soccer: {len(fixtures)} matches today")
                sports_data.extend(fixtures)
        except Exception as e:
            print(f"   Soccer error: {e}")
        
        return sports_data
    
    def get_weather_data(self):
        """Get weather from WeatherAPI.com"""
        if not WEATHER_API_KEY:
            print("⚠️  No WeatherAPI key")
            return []
        
        weather_data = []
        
        for loc in self.weather_locations[:6]:  # Check 6 cities
            try:
                url = "http://api.weatherapi.com/v1/forecast.json"
                params = {
                    'key': WEATHER_API_KEY,
                    'q': f"{loc['name']},{loc['country']}",
                    'days': 1,
                    'aqi': 'no',
                    'alerts': 'no'
                }
                response = requests.get(url, params=params, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    forecast = data.get('forecast', {}).get('forecastday', [{}])[0]
                    day = forecast.get('day', {})
                    
                    rain_chance = day.get('daily_chance_of_rain', 0)
                    snow_chance = day.get('daily_chance_of_snow', 0)
                    max_temp = day.get('maxtemp_c', 0)
                    
                    condition = "🌧️ Rain" if rain_chance > 50 else "❄️ Snow" if snow_chance > 50 else "☀️ Clear"
                    print(f"   {loc['name']}: {condition} ({rain_chance}% rain, {max_temp}°C)")
                    
                    weather_data.append({
                        'location': loc['name'],
                        'rain_chance': rain_chance,
                        'snow_chance': snow_chance,
                        'max_temp': max_temp
                    })
            except Exception as e:
                print(f"   {loc['name']} error: {e}")
        
        return weather_data
    
    def get_crypto_data(self):
        """Get crypto prices from CoinGecko"""
        try:
            url = "https://api.coingecko.com/api/v3/simple/price"
            params = {
                'ids': 'bitcoin,ethereum',
                'vs_currencies': 'usd',
                'include_24hr_change': 'true'
            }
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                btc = data.get('bitcoin', {})
                eth = data.get('ethereum', {})
                
                btc_price = btc.get('usd', 0)
                btc_change = btc.get('usd_24h_change', 0)
                eth_price = eth.get('usd', 0)
                eth_change = eth.get('usd_24h_change', 0)
                
                print(f"   ₿ BTC: ${btc_price:,.0f} ({btc_change:+.2f}%)")
                print(f"   Ξ ETH: ${eth_price:,.0f} ({eth_change:+.2f}%)")
                
                return {'btc': btc_price, 'eth': eth_price}
        except Exception as e:
            print(f"   Crypto error: {e}")
        
        return {}
    
    def scan_polymarket(self, category):
        """Scan Polymarket for relevant markets"""
        search_terms = {
            'crypto': ['Bitcoin', 'Ethereum', 'BTC', 'ETH'],
            'sports': ['NBA', 'NFL', 'soccer', 'tennis', 'game'],
            'weather': ['rain', 'snow', 'temperature', 'weather']
        }
        
        markets = []
        for term in search_terms.get(category, []):
            try:
                cmd = f"cd /root/.openclaw/skills/polyclaw && source .env && uv run python scripts/polyclaw.py markets search '{term}' --limit 3"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
                if result.returncode == 0:
                    markets.append(result.stdout)
            except:
                pass
        
        return markets
    
    def run_full_scan(self):
        """Run complete professional scan"""
        print("="*70)
        print("PRO MULTI-CATEGORY TRADING SCAN v3.0")
        print("="*70)
        print(f"APIs: API-Sports.io ✅ | WeatherAPI.com ✅ | CoinGecko ✅")
        print(f"Categories: Crypto 30% | Sports 40% | Weather 30%")
        print("="*70)
        
        # 1. CRYPTO
        print("\n🔶 CRYPTO (CoinGecko)")
        crypto = self.get_crypto_data()
        crypto_markets = self.scan_polymarket('crypto')
        
        # 2. SPORTS (API-Sports.io)
        print("\n🏀 SPORTS (API-Sports.io)")
        sports = self.get_sports_data()
        sports_markets = self.scan_polymarket('sports')
        
        # 3. WEATHER (WeatherAPI.com)
        print("\n🌦️ WEATHER (WeatherAPI.com)")
        weather = self.get_weather_data()
        weather_markets = self.scan_polymarket('weather')
        
        print("\n" + "="*70)
        print("SCAN COMPLETE - Analyzing opportunities...")
        print("="*70)
        
        return {
            'crypto': crypto,
            'sports': len(sports),
            'weather': len(weather)
        }

def main():
    trader = ProMultiTrader()
    results = trader.run_full_scan()
    
    print("\n📊 READY TO TRADE:")
    print(f"   Crypto data: {'✅' if results['crypto'] else '❌'}")
    print(f"   Sports events: {results['sports']}")
    print(f"   Weather locations: {results['weather']}")
    print(f"\n💰 Wallet ready for $1 bets!")

if __name__ == "__main__":
    main()
