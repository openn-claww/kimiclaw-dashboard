# Polymarket Trading Dashboard - Complete API Documentation
## For React + Tailwind Build

---

## 🔗 ESSENTIAL API ENDPOINTS

### 1. POLYMARKET GAMMA API (Primary Data Source)

**Base URL:** `https://gamma-api.polymarket.com`

#### Get Market Details
```
GET /markets/{market_id}
```
**Response:**
```json
{
  "id": "1369917",
  "question": "Will the price of Bitcoin be above $66,000 on February 19?",
  "slug": "bitcoin-above-66k-on-february-19",
  "conditionId": "0xf972542880343e9bb9fc75aec332b34d1becf0e0b8a7aee37b3c6f43f694ce7a",
  "outcomes": ["Yes", "No"],
  "outcomePrices": ["0.9995", "0.0005"],
  "volume": 1015223.556714,
  "volume24hr": 640794.887543,
  "liquidity": 660691.06194,
  "endDate": "2026-02-19T17:00:00Z",
  "active": true,
  "closed": true,
  "resolved": false,
  "outcome": null
}
```

#### Get Trending Markets
```
GET /markets?limit=20&sort=volume&order=desc
```

#### Get All Markets
```
GET /markets?limit=100&offset=0
```

---

### 2. POLYMARKET DATA API (User Data)

**Base URL:** `https://data-api.polymarket.com`

#### Get User Positions
```
GET /positions?user={wallet_address}
```
**Headers:**
```
Authorization: Bearer {optional_jwt}
```

**Response:**
```json
[
  {
    "id": "9f3b68e5",
    "marketId": "1369917",
    "marketQuestion": "Will the price of Bitcoin be above $66,000 on February 19?",
    "side": "YES",
    "size": 1.0,
    "entryPrice": 0.525,
    "currentPrice": 1.0,
    "pnl": 0.0,
    "status": "open"
  }
]
```

#### Get User Activity/Trades
```
GET /activity?user={wallet_address}&limit=50
```

#### Get User Portfolio Value
```
GET /portfolio?user={wallet_address}
```

---

### 3. POLYGON BLOCKCHAIN API (Wallet Data)

**Base URL:** `https://api.polygonscan.com/api`

#### Get Token Balance
```
GET /api?module=account&action=tokenbalance
  &contractaddress=0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174
  &address={wallet_address}
  &tag=latest
  &apikey={YOUR_API_KEY}
```

**Response:**
```json
{
  "status": "1",
  "message": "OK",
  "result": "8137619"  // 8.137619 USDC.e (divide by 1e6)
}
```

#### Get Token Transfers
```
GET /api?module=account&action=tokentx
  &contractaddress=0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174
  &address={wallet_address}
  &startblock=0&endblock=99999999
  &sort=desc
  &apikey={YOUR_API_KEY}
```

---

### 4. POLYMARKET CLOB API (Order Book)

**Base URL:** `https://clob.polymarket.com`

#### Get Order Book
```
GET /book/{token_id}
```

#### Get Market Prices
```
GET /prices/{market_id}
```

---

## 📊 SMART CONTRACT ADDRESSES

| Contract | Address | Purpose |
|----------|---------|---------|
| **USDC.e** | `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174` | Collateral token |
| **CTF (Conditional Tokens)** | `0x4D97DCd97eC945f40cF65F87097ACe5EA0476045` | Position tokens |
| **CTF Exchange** | `0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E` | Trading |
| **Neg Risk Adapter** | `0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296` | Negative risk markets |

---

## 🔧 SDKs & LIBRARIES

### Python (for backend/scripts)
```bash
pip install py-clob-client web3 python-dotenv
```

### JavaScript/TypeScript (for React)
```bash
npm install @polymarket/clob-client ethers
# or
yarn add @polymarket/clob-client ethers
```

### React Hook Example
```typescript
// hooks/usePolymarket.ts
import { useState, useEffect } from 'react';

const GAMMA_API = 'https://gamma-api.polymarket.com';

export const useMarket = (marketId: string) => {
  const [market, setMarket] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${GAMMA_API}/markets/${marketId}`)
      .then(res => res.json())
      .then(data => {
        setMarket(data);
        setLoading(false);
      });
  }, [marketId]);

  return { market, loading };
};
```

---

## 📱 REACT DASHBOARD STRUCTURE

### Recommended Component Tree
```
src/
├── components/
│   ├── WalletCard.tsx          # USDC.e + POL balance
│   ├── PositionList.tsx        # All open/closed positions
│   ├── PositionCard.tsx        # Individual position
│   ├── MarketDetail.tsx        # Market info + prices
│   ├── PnLChart.tsx            # Profit/loss over time
│   ├── MoneyFlow.tsx           # Visual flow diagram
│   ├── TradeHistory.tsx        # Past trades table
│   └── DailyReport.tsx         # EOD summary
├── hooks/
│   ├── useWallet.ts            # Wallet balance hook
│   ├── usePositions.ts         # Positions hook
│   ├── useMarkets.ts           # Markets data hook
│   └── useAutoRefresh.ts       # 30s refresh hook
├── utils/
│   ├── formatters.ts           # Number/date formatters
│   ├── calculations.ts         # PnL calculations
│   └── api.ts                  # API call wrappers
├── types/
│   └── index.ts                # TypeScript interfaces
└── App.tsx
```

---

## 🎨 TAILWIND STYLES (Dark Theme)

```css
/* tailwind.config.js */
module.exports = {
  theme: {
    extend: {
      colors: {
        'pm-bg': '#0a0a0f',
        'pm-card': '#151520',
        'pm-border': '#252535',
        'pm-accent': '#00d4ff',
        'pm-success': '#00ff88',
        'pm-danger': '#ff4757',
      }
    }
  }
}
```

---

## 🔐 WALLET CONNECTION

### Using ethers.js
```typescript
import { ethers } from 'ethers';

const connectWallet = async () => {
  if (window.ethereum) {
    const provider = new ethers.BrowserProvider(window.ethereum);
    const signer = await provider.getSigner();
    const address = await signer.getAddress();
    return { provider, signer, address };
  }
  throw new Error('MetaMask not found');
};
```

---

## 📊 DATA FLOW DIAGRAM

```
┌─────────────────────────────────────────────────────────────┐
│                      YOUR WALLET                            │
│                 (MetaMask - 0x557A...)                       │
│  ┌─────────────────┐  ┌─────────────────┐                   │
│  │   USDC.e: $8.13 │  │   POL: 2.46     │                   │
│  └────────┬────────┘  └─────────────────┘                   │
└───────────┼─────────────────────────────────────────────────┘
            │
            │ 1. Deposit USDC.e
            ▼
┌─────────────────────────────────────────────────────────────┐
│                   POLYMARKET SMART CONTRACTS                 │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  CTF Contract (0x4D97...)                           │    │
│  │  ┌─────────────┐    ┌─────────────┐                │    │
│  │  │ Split $10   │───▶│ YES: 10     │                │    │
│  │  │             │    │ NO: 10      │                │    │
│  │  └─────────────┘    └──────┬──────┘                │    │
│  │                            │                       │    │
│  │                            │ 2. Sell NO tokens     │    │
│  │                            ▼                       │    │
│  │                     ┌─────────────┐                │    │
│  │                     │ CLOB DEX    │                │    │
│  │                     │ Sell NO @   │                │    │
│  │                     │ $0.35 = $3.5│                │    │
│  │                     └──────┬──────┘                │    │
│  │                            │                       │    │
│  │                            ▼                       │    │
│  │                     ┌─────────────┐                │    │
│  │                     │ Net: $6.5   │                │    │
│  │                     │ YES: 10     │                │    │
│  │                     │ (Effective  │                │    │
│  │                     │  price $0.65│                │    │
│  │                     └─────────────┘                │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  MARKET RESOLVES (BTC > $66K) ✅                     │    │
│  │                                                     │    │
│  │  YES tokens become redeemable for $1.00 each       │    │
│  │                                                     │    │
│  │  3. Call redeemPositions()                         │    │
│  │     YES: 10 × $1.00 = $10.00                       │    │
│  │     (Profit: $10 - $6.5 = $3.5)                    │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
            │
            │ 4. USDC.e returned
            ▼
┌─────────────────────────────────────────────────────────────┐
│                   YOUR WALLET (AFTER)                        │
│                                                              │
│  ┌─────────────────┐  ┌─────────────────┐                   │
│  │   USDC.e: $18.13│  │   POL: 2.46     │                   │
│  │   (+$10 from    │  │   (gas spent)   │                   │
│  │    redemption)  │  │                 │                   │
│  └─────────────────┘  └─────────────────┘                   │
└─────────────────────────────────────────────────────────────┘

FEES BREAKDOWN:
├── Gas for Split: ~0.15 POL (~$0.015)
├── Gas for CLOB Sell: ~0.05 POL (~$0.005)
├── Gas for Redeem: ~0.10 POL (~$0.010)
├── Platform Fee: 0% (Polymarket doesn't charge)
└── Total Gas: ~$0.03 per trade
```

---

## 🚀 QUICK START FOR REACT APP

```bash
# 1. Create React app with TypeScript + Tailwind
npx create-react-app polymarket-dashboard --template typescript
cd polymarket-dashboard
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p

# 2. Install dependencies
npm install ethers @polymarket/clob-client recharts date-fns

# 3. Start development
npm start
```

---

## 📞 SUPPORT & RESOURCES

- **Polymarket Docs:** https://docs.polymarket.com
- **Gamma API Docs:** https://docs.polymarket.com/#gamma-api
- **CLOB Client:** https://github.com/Polymarket/py-clob-client
- **Discord:** https://discord.gg/polymarket

---

**Your Wallet:** `0x557A656C110a9eFdbFa28773DE4aCc2c3924a274`

**Dashboard Repo:** https://github.com/openn-claww/kimiclaw-dashboard
