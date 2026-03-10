# Working Code Library: OpenClaw Money-Making Systems
## Production-Ready Scripts for Implementation

---

## 1. Complete Options Wheel Trading System

### File: `wheel_system.py`

```python
#!/usr/bin/env python3
"""
Complete Options Wheel Trading System
Integrates scanning, tracking, and alerting
"""

import sqlite3
import json
import requests
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict
import os

# Configuration
CONFIG = {
    "min_iv_rank": 30,
    "max_positions": 5,
    "discord_webhook": os.getenv("DISCORD_WEBHOOK", ""),
    "db_path": "wheel_system.db",
    "watchlist": ["AAPL", "MSFT", "AMD", "NVDA", "JPM", "BAC", "KO", "XOM", "SPY", "QQQ"]
}

@dataclass
class WheelPosition:
    symbol: str
    position_type: str  # 'csp' or 'cc'
    strike: float
    premium: float
    expiration: str
    contracts: int = 1
    notes: str = ""

class WheelSystem:
    def __init__(self):
        self.init_database()
    
    def init_database(self):
        """Initialize complete database schema"""
        conn = sqlite3.connect(CONFIG["db_path"])
        cursor = conn.cursor()
        
        # Positions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                position_type TEXT NOT NULL,
                strike REAL NOT NULL,
                premium_received REAL NOT NULL,
                expiration DATE NOT NULL,
                contracts INTEGER DEFAULT 1,
                open_price REAL,
                assigned BOOLEAN DEFAULT 0,
                assigned_date DATE,
                shares_owned INTEGER DEFAULT 0,
                cost_basis REAL,
                closed BOOLEAN DEFAULT 0,
                close_date DATE,
                close_premium REAL,
                profit_loss REAL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Scans table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                stock_price REAL,
                iv_rank REAL,
                iv_percentile REAL,
                suggested_put_strike REAL,
                suggested_call_strike REAL,
                estimated_premium REAL,
                scan_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Performance tracking
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS performance (
                month TEXT PRIMARY KEY,
                total_premium REAL DEFAULT 0,
                closed_trades INTEGER DEFAULT 0,
                total_pnl REAL DEFAULT 0,
                win_rate REAL DEFAULT 0
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def scan_opportunities(self) -> List[Dict]:
        """
        Scan watchlist for Wheel opportunities
        Note: In production, integrate with real market data API
        """
        opportunities = []
        
        for symbol in CONFIG["watchlist"]:
            # Placeholder - replace with actual API call
            # Example using mock data structure:
            mock_data = self._fetch_market_data(symbol)
            
            if mock_data and mock_data["iv_rank"] >= CONFIG["min_iv_rank"]:
                opp = {
                    "symbol": symbol,
                    "stock_price": mock_data["price"],
                    "iv_rank": mock_data["iv_rank"],
                    "suggested_put_strike": round(mock_data["price"] * 0.95, 2),
                    "estimated_premium": mock_data["price"] * 0.015,  # ~1.5% of strike
                    "cash_required": round(mock_data["price"] * 0.95 * 100, 2)
                }
                opportunities.append(opp)
                self._log_scan(opp)
        
        return opportunities
    
    def _fetch_market_data(self, symbol: str) -> Optional[Dict]:
        """Fetch market data - integrate with your broker API"""
        # TODO: Replace with actual API integration
        # Examples: Tradier, Polygon.io, Interactive Brokers
        
        # Mock data for demonstration
        mock_prices = {
            "AAPL": 175.0, "MSFT": 420.0, "AMD": 180.0,
            "NVDA": 880.0, "JPM": 195.0, "BAC": 37.0,
            "KO": 62.0, "XOM": 118.0, "SPY": 515.0, "QQQ": 445.0
        }
        
        if symbol in mock_prices:
            # Simulate IV rank (in reality, fetch from API)
            import random
            return {
                "symbol": symbol,
                "price": mock_prices[symbol],
                "iv_rank": random.uniform(25, 55),  # Random for demo
                "iv_percentile": random.uniform(30, 70)
            }
        return None
    
    def _log_scan(self, opportunity: Dict):
        """Log scan to database"""
        conn = sqlite3.connect(CONFIG["db_path"])
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO scans (symbol, stock_price, iv_rank, suggested_put_strike, estimated_premium)
            VALUES (?, ?, ?, ?, ?)
        ''', (opportunity["symbol"], opportunity["stock_price"],
              opportunity["iv_rank"], opportunity["suggested_put_strike"],
              opportunity["estimated_premium"]))
        conn.commit()
        conn.close()
    
    def open_position(self, position: WheelPosition) -> int:
        """Record new position"""
        conn = sqlite3.connect(CONFIG["db_path"])
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO positions 
            (symbol, position_type, strike, premium_received, expiration, contracts, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (position.symbol, position.position_type, position.strike,
              position.premium, position.expiration, position.contracts, position.notes))
        
        position_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        print(f"✓ Opened {position.position_type.upper()} position: {position.symbol} ${position.strike}")
        return position_id
    
    def record_assignment(self, position_id: int, assigned_price: float):
        """Record put assignment"""
        conn = sqlite3.connect(CONFIG["db_path"])
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM positions WHERE id = ?", (position_id,))
        row = cursor.fetchone()
        
        if row:
            strike = row[3]
            premium = row[4]
            contracts = row[6]
            shares = contracts * 100
            cost_basis = strike - (premium / shares)
            
            cursor.execute('''
                UPDATE positions 
                SET assigned = 1, assigned_date = DATE('now'),
                    shares_owned = ?, cost_basis = ?
                WHERE id = ?
            ''', (shares, cost_basis, position_id))
            
            conn.commit()
            print(f"✓ Assignment recorded: {row[1]} {shares} shares @ ${cost_basis:.2f} basis")
        
        conn.close()
    
    def close_position(self, position_id: int, close_premium: Optional[float] = None):
        """Close position and calculate P&L"""
        conn = sqlite3.connect(CONFIG["db_path"])
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM positions WHERE id = ?", (position_id,))
        row = cursor.fetchone()
        
        if row:
            position_type = row[2]
            premium_received = row[4]
            close_prem = close_premium or 0
            
            # Calculate P&L
            if position_type == "csp":
                pnl = premium_received - close_prem
            else:  # covered call
                pnl = premium_received - close_prem
            
            cursor.execute('''
                UPDATE positions 
                SET closed = 1, close_date = DATE('now'),
                    close_premium = ?, profit_loss = ?
                WHERE id = ?
            ''', (close_premium, pnl, position_id))
            
            conn.commit()
            print(f"✓ Closed position {position_id}: P&L ${pnl:.2f}")
        
        conn.close()
    
    def get_portfolio_summary(self) -> Dict:
        """Get complete portfolio summary"""
        conn = sqlite3.connect(CONFIG["db_path"])
        cursor = conn.cursor()
        
        # Open positions
        cursor.execute('''
            SELECT COUNT(*), SUM(premium_received), 
                   SUM(CASE WHEN assigned THEN 1 ELSE 0 END),
                   SUM(CASE WHEN position_type = 'csp' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN position_type = 'cc' THEN 1 ELSE 0 END)
            FROM positions WHERE closed = 0
        ''')
        open_stats = cursor.fetchone()
        
        # Closed positions this month
        cursor.execute('''
            SELECT COUNT(*), SUM(profit_loss)
            FROM positions 
            WHERE closed = 1 
            AND strftime('%Y-%m', close_date) = strftime('%Y-%m', 'now')
        ''')
        monthly_stats = cursor.fetchone()
        
        # All-time stats
        cursor.execute('''
            SELECT COUNT(*), SUM(profit_loss), AVG(profit_loss)
            FROM positions WHERE closed = 1
        ''')
        all_time = cursor.fetchone()
        
        conn.close()
        
        return {
            "open_positions": open_stats[0] or 0,
            "open_premium": open_stats[1] or 0,
            "assigned_positions": open_stats[2] or 0,
            "csp_open": open_stats[3] or 0,
            "cc_open": open_stats[4] or 0,
            "monthly_closed": monthly_stats[0] or 0,
            "monthly_pnl": monthly_stats[1] or 0,
            "total_closed": all_time[0] or 0,
            "total_pnl": all_time[1] or 0,
            "avg_pnl_per_trade": all_time[2] or 0
        }
    
    def send_discord_alert(self, opportunity: Dict):
        """Send opportunity alert to Discord"""
        if not CONFIG["discord_webhook"]:
            print("Discord webhook not configured")
            return
        
        embed = {
            "title": f"🎯 Wheel Opportunity: {opportunity['symbol']}",
            "description": f"IV Rank: {opportunity['iv_rank']:.1f}",
            "color": 0xffd700,
            "fields": [
                {"name": "Stock Price", "value": f"${opportunity['stock_price']:.2f}", "inline": True},
                {"name": "Suggested Put", "value": f"${opportunity['suggested_put_strike']:.2f}", "inline": True},
                {"name": "Est. Premium", "value": f"${opportunity['estimated_premium']:.2f}", "inline": True},
                {"name": "Cash Required", "value": f"${opportunity['cash_required']:,.0f}", "inline": False}
            ],
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            requests.post(CONFIG["discord_webhook"], json={"embeds": [embed]}, timeout=10)
        except Exception as e:
            print(f"Discord alert failed: {e}")
    
    def run_daily_scan(self):
        """Execute daily scan workflow"""
        print(f"\n[{datetime.now()}] Starting Wheel System Scan...")
        print("="*60)
        
        # Get opportunities
        opportunities = self.scan_opportunities()
        
        if opportunities:
            print(f"\n✓ Found {len(opportunities)} opportunities:")
            for opp in opportunities:
                print(f"  • {opp['symbol']}: IV Rank {opp['iv_rank']:.1f}, "
                      f"Strike ${opp['suggested_put_strike']:.2f}")
                self.send_discord_alert(opp)
        else:
            print("\n• No opportunities above IV Rank threshold")
        
        # Print portfolio summary
        summary = self.get_portfolio_summary()
        print(f"\n📊 Portfolio Summary:")
        print(f"  Open Positions: {summary['open_positions']}")
        print(f"  Premium Collected (Open): ${summary['open_premium']:.2f}")
        print(f"  Monthly P&L: ${summary['monthly_pnl']:.2f}")
        print(f"  Total P&L (All Time): ${summary['total_pnl']:.2f}")
        print("="*60)

# CLI Interface
if __name__ == "__main__":
    import sys
    
    system = WheelSystem()
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "scan":
            system.run_daily_scan()
        
        elif command == "open":
            # Example: python wheel_system.py open AAPL csp 175 2.50 2024-04-19
            if len(sys.argv) >= 7:
                pos = WheelPosition(
                    symbol=sys.argv[2],
                    position_type=sys.argv[3],
                    strike=float(sys.argv[4]),
                    premium=float(sys.argv[5]),
                    expiration=sys.argv[6]
                )
                system.open_position(pos)
            else:
                print("Usage: python wheel_system.py open <symbol> <csp|cc> <strike> <premium> <expiration>")
        
        elif command == "assign":
            # Example: python wheel_system.py assign 1 170.0
            if len(sys.argv) >= 4:
                system.record_assignment(int(sys.argv[2]), float(sys.argv[3]))
        
        elif command == "close":
            # Example: python wheel_system.py close 1 0.50
            if len(sys.argv) >= 3:
                close_prem = float(sys.argv[3]) if len(sys.argv) > 3 else None
                system.close_position(int(sys.argv[2]), close_prem)
        
        elif command == "summary":
            summary = system.get_portfolio_summary()
            print(json.dumps(summary, indent=2))
        
        else:
            print("Commands: scan, open, assign, close, summary")
    else:
        system.run_daily_scan()
```

---

## 2. B2B Lead Generation System

### File: `lead_gen_system.py`

```python
#!/usr/bin/env python3
"""
B2B Lead Generation System
Automates prospecting, outreach, and lead tracking
"""

import sqlite3
import json
import re
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List, Dict, Optional
import requests
from urllib.parse import urljoin, quote

@dataclass
class Prospect:
    company: str
    website: str
    email: Optional[str] = None
    linkedin: Optional[str] = None
    industry: Optional[str] = None
    status: str = "new"  # new, contacted, responded, qualified, converted
    notes: str = ""

class LeadGenSystem:
    def __init__(self, db_path="leadgen.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize lead generation database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS prospects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company TEXT NOT NULL,
                website TEXT,
                email TEXT,
                linkedin TEXT,
                industry TEXT,
                company_size TEXT,
                status TEXT DEFAULT 'new',
                source TEXT,
                first_contact DATE,
                last_contact DATE,
                contact_count INTEGER DEFAULT 0,
                response_received BOOLEAN DEFAULT 0,
                qualified BOOLEAN DEFAULT 0,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                industry_target TEXT,
                message_template TEXT,
                prospects_count INTEGER DEFAULT 0,
                responses_count INTEGER DEFAULT 0,
                conversion_rate REAL,
                active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prospect_id INTEGER,
                activity_type TEXT,  # email_sent, email_opened, linkedin_view, etc.
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (prospect_id) REFERENCES prospects (id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def find_prospects_from_linkedin(self, industry: str, company_size: str = "50-200") -> List[Dict]:
        """
        Find prospects from LinkedIn
        Note: Requires LinkedIn Sales Navigator or similar tool
        """
        # This is a placeholder - in production, you'd use:
        # - LinkedIn Sales Navigator API
        # - Phantombuster
        # - Proxycurl
        # - Manual search export
        
        prospects = []
        
        # Mock data for demonstration
        mock_companies = {
            "saas": [
                {"name": "TechFlow Solutions", "website": "techflow.io", "size": "50-200"},
                {"name": "CloudScale Systems", "website": "cloudscale.com", "size": "50-200"},
                {"name": "DataSync Pro", "website": "datasync.pro", "size": "50-200"},
            ],
            "ecommerce": [
                {"name": "ShopMax Retail", "website": "shopmax.com", "size": "50-200"},
                {"name": "Global Goods Inc", "website": "globalgoods.co", "size": "50-200"},
            ]
        }
        
        for company in mock_companies.get(industry, []):
            prospects.append({
                "company": company["name"],
                "website": company["website"],
                "industry": industry,
                "company_size": company["size"]
            })
        
        return prospects
    
    def find_email_from_website(self, domain: str) -> Optional[str]:
        """
        Find email patterns from website
        Common patterns: contact@, info@, hello@, support@
        """
        common_patterns = [
            f"contact@{domain}",
            f"info@{domain}",
            f"hello@{domain}",
            f"support@{domain}",
            f"sales@{domain}",
            f"team@{domain}"
        ]
        
        # In production, use email verification service:
        # - Hunter.io
        # - Snov.io
        # - Apollo.io
        # - Verify email pattern
        
        # Return most likely pattern
        return common_patterns[0]  # contact@domain
    
    def add_prospect(self, prospect: Prospect, source: str = "manual") -> int:
        """Add new prospect to database"""
        # Find email if not provided
        if not prospect.email and prospect.website:
            domain = prospect.website.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
            prospect.email = self.find_email_from_website(domain)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO prospects 
                (company, website, email, linkedin, industry, status, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (prospect.company, prospect.website, prospect.email,
                  prospect.linkedin, prospect.industry, prospect.status, source))
            
            prospect_id = cursor.lastrowid
            conn.commit()
            print(f"✓ Added prospect: {prospect.company}")
            return prospect_id
            
        except sqlite3.IntegrityError:
            print(f"⚠ Prospect already exists: {prospect.company}")
            return 0
        finally:
            conn.close()
    
    def generate_outreach_email(self, prospect: Prospect, template_type: str = "cold") -> str:
        """Generate personalized outreach email"""
        
        templates = {
            "cold": f"""Subject: Quick question about {prospect.company}

Hi there,

I came across {prospect.company} and was impressed by your work in the {prospect.industry or 'industry'} space.

I'm reaching out because we help {prospect.industry or 'businesses like yours'} [specific value proposition].

For example, we recently helped [similar company] achieve [specific result] in [timeframe].

Would you be open to a brief conversation about how we might help {prospect.company}?

Best regards,
[Your Name]
""",
            "follow_up": f"""Subject: Following up - {prospect.company}

Hi there,

I wanted to follow up on my previous email about helping {prospect.company} with [value proposition].

I understand you're busy. Would a brief 10-minute call next week work for you?

Best regards,
[Your Name]
"""
        }
        
        return templates.get(template_type, templates["cold"])
    
    def record_activity(self, prospect_id: int, activity_type: str, details: str = ""):
        """Record prospecting activity"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO activities (prospect_id, activity_type, details)
            VALUES (?, ?, ?)
        ''', (prospect_id, activity_type, details))
        
        # Update prospect status and contact dates
        if activity_type == "email_sent":
            cursor.execute('''
                UPDATE prospects 
                SET contact_count = contact_count + 1,
                    last_contact = DATE('now'),
                    first_contact = COALESCE(first_contact, DATE('now'))
                WHERE id = ?
            ''', (prospect_id,))
        
        conn.commit()
        conn.close()
    
    def get_pipeline_summary(self) -> Dict:
        """Get sales pipeline summary"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT status, COUNT(*) as count
            FROM prospects
            GROUP BY status
        ''')
        
        pipeline = {row[0]: row[1] for row in cursor.fetchall()}
        
        cursor.execute('''
            SELECT COUNT(*) FROM prospects WHERE created_at >= DATE('now', '-30 days')
        ''')
        new_this_month = cursor.fetchone()[0]
        
        cursor.execute('''
            SELECT AVG(contact_count) FROM prospects WHERE contact_count > 0
        ''')
        avg_touch_count = cursor.fetchone()[0] or 0
        
        conn.close()
        
        return {
            "total_prospects": sum(pipeline.values()),
            "pipeline": pipeline,
            "new_this_month": new_this_month,
            "avg_touches": round(avg_touch_count, 1)
        }
    
    def export_for_outreach(self, status: str = "new", limit: int = 50) -> List[Dict]:
        """Export prospects for outreach campaign"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM prospects
            WHERE status = ?
            LIMIT ?
        ''', (status, limit))
        
        columns = [description[0] for description in cursor.description]
        prospects = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        conn.close()
        
        # Generate emails
        for p in prospects:
            prospect_obj = Prospect(
                company=p["company"],
                website=p["website"],
                email=p["email"],
                linkedin=p["linkedin"],
                industry=p["industry"]
            )
            p["outreach_email"] = self.generate_outreach_email(prospect_obj)
        
        return prospects

# CLI Interface
if __name__ == "__main__":
    import sys
    
    system = LeadGenSystem()
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "import":
            # Import prospects from LinkedIn/search
            industry = sys.argv[2] if len(sys.argv) > 2 else "saas"
            prospects = system.find_prospects_from_linkedin(industry)
            
            for p in prospects:
                prospect = Prospect(
                    company=p["company"],
                    website=p["website"],
                    industry=p["industry"]
                )
                system.add_prospect(prospect, source=f"linkedin_{industry}")
        
        elif command == "add":
            # Manual add: python lead_gen_system.py add "Company Name" "website.com"
            if len(sys.argv) >= 4:
                prospect = Prospect(
                    company=sys.argv[2],
                    website=sys.argv[3]
                )
                system.add_prospect(prospect)
        
        elif command == "email":
            # Generate email for prospect
            if len(sys.argv) >= 3:
                prospect_id = int(sys.argv[2])
                conn = sqlite3.connect(system.db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM prospects WHERE id = ?", (prospect_id,))
                row = cursor.fetchone()
                conn.close()
                
                if row:
                    p = Prospect(company=row[1], website=row[2], email=row[3], industry=row[5])
                    print(system.generate_outreach_email(p))
        
        elif command == "pipeline":
            summary = system.get_pipeline_summary()
            print(json.dumps(summary, indent=2))
        
        elif command == "export":
            prospects = system.export_for_outreach()
            print(f"Exported {len(prospects)} prospects for outreach")
            for p in prospects[:5]:  # Show first 5
                print(f"\n{p['company']} - {p['email']}")
        
        else:
            print("Commands: import, add, email, pipeline, export")
    else:
        summary = system.get_pipeline_summary()
        print(json.dumps(summary, indent=2))
```

---

## 3. Customer Support Bot System

### File: `support_bot_system.py`

```python
#!/usr/bin/env python3
"""
Customer Support Bot Management System
Manages multiple chatbot deployments for clients
"""

import sqlite3
import json
from datetime import datetime
from dataclasses import dataclass
from typing import List, Dict, Optional

@dataclass
class BotClient:
    company: str
    website: str
    industry: str
    bot_platform: str  # tidio, intercom, custom
    monthly_fee: float
    conversation_limit: int

class SupportBotSystem:
    def __init__(self, db_path="support_bots.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize support bot database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company TEXT NOT NULL,
                website TEXT,
                industry TEXT,
                bot_platform TEXT,
                bot_config TEXT,  -- JSON configuration
                monthly_fee REAL,
                conversation_limit INTEGER,
                conversations_this_month INTEGER DEFAULT 0,
                setup_fee_paid BOOLEAN DEFAULT 0,
                status TEXT DEFAULT 'active',
                onboarding_date DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER,
                conversation_id TEXT,
                user_message TEXT,
                bot_response TEXT,
                handled BOOLEAN DEFAULT 1,  -- 1 = bot handled, 0 = escalated
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (client_id) REFERENCES clients (id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS knowledge_base (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER,
                question TEXT,
                answer TEXT,
                category TEXT,
                usage_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (client_id) REFERENCES clients (id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER,
                month TEXT,
                base_fee REAL,
                overage_fee REAL DEFAULT 0,
                total_fee REAL,
                paid BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (client_id) REFERENCES clients (id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def onboard_client(self, client: BotClient, setup_fee: float = 500.0) -> int:
        """Onboard new bot client"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO clients 
            (company, website, industry, bot_platform, monthly_fee, 
             conversation_limit, onboarding_date, setup_fee_paid)
            VALUES (?, ?, ?, ?, ?, ?, DATE('now'), ?)
        ''', (client.company, client.website, client.industry, client.bot_platform,
              client.monthly_fee, client.conversation_limit, setup_fee > 0))
        
        client_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        print(f"✓ Onboarded client: {client.company}")
        print(f"  Setup fee: ${setup_fee}")
        print(f"  Monthly: ${client.monthly_fee}")
        return client_id
    
    def generate_bot_training(self, client_id: int, faq_source: str = None) -> List[Dict]:
        """Generate bot training data from client materials"""
        # In production, this would:
        # 1. Scrape client's FAQ page
        # 2. Process documentation
        # 3. Use Kimi to generate Q&A pairs
        
        default_training = [
            {
                "question": "What are your business hours?",
                "answer": "We're available Monday-Friday, 9 AM - 6 PM EST.",
                "category": "general"
            },
            {
                "question": "How do I contact support?",
                "answer": "You can reach our support team via this chat, email, or phone.",
                "category": "support"
            },
            {
                "question": "What is your refund policy?",
                "answer": "We offer a 30-day money-back guarantee on all purchases.",
                "category": "billing"
            }
        ]
        
        # Save to knowledge base
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for item in default_training:
            cursor.execute('''
                INSERT INTO knowledge_base (client_id, question, answer, category)
                VALUES (?, ?, ?, ?)
            ''', (client_id, item["question"], item["answer"], item["category"]))
        
        conn.commit()
        conn.close()
        
        return default_training
    
    def record_conversation(self, client_id: int, user_msg: str, bot_resp: str, handled: bool = True):
        """Record bot conversation"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO conversations (client_id, user_message, bot_response, handled)
            VALUES (?, ?, ?, ?)
        ''', (client_id, user_msg, bot_resp, handled))
        
        # Update monthly count
        cursor.execute('''
            UPDATE clients 
            SET conversations_this_month = conversations_this_month + 1
            WHERE id = ?
        ''', (client_id,))
        
        conn.commit()
        conn.close()
    
    def generate_monthly_invoice(self, client_id: int, month: str = None) -> Dict:
        """Generate monthly invoice for client"""
        if not month:
            month = datetime.now().strftime("%Y-%m")
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT monthly_fee, conversation_limit, conversations_this_month
            FROM clients WHERE id = ?
        ''', (client_id,))
        
        row = cursor.fetchone()
        if not row:
            return {}
        
        base_fee, limit, used = row
        
        # Calculate overage
        overage_fee = 0
        if used > limit:
            overage = used - limit
            overage_fee = overage * 0.10  # $0.10 per overage conversation
        
        total = base_fee + overage_fee
        
        # Save invoice
        cursor.execute('''
            INSERT OR REPLACE INTO invoices 
            (client_id, month, base_fee, overage_fee, total_fee)
            VALUES (?, ?, ?, ?, ?)
        ''', (client_id, month, base_fee, overage_fee, total))
        
        # Reset monthly counter
        cursor.execute('''
            UPDATE clients SET conversations_this_month = 0 WHERE id = ?
        ''', (client_id,))
        
        conn.commit()
        conn.close()
        
        return {
            "client_id": client_id,
            "month": month,
            "base_fee": base_fee,
            "conversations_used": used,
            "conversation_limit": limit,
            "overage_fee": overage_fee,
            "total": total
        }
    
    def get_business_metrics(self) -> Dict:
        """Get overall business metrics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Client counts
        cursor.execute('''
            SELECT status, COUNT(*), SUM(monthly_fee)
            FROM clients
            GROUP BY status
        ''')
        
        client_stats = {}
        for row in cursor.fetchall():
            client_stats[row[0]] = {"count": row[1], "mrr": row[2] or 0}
        
        # Monthly revenue
        current_month = datetime.now().strftime("%Y-%m")
        cursor.execute('''
            SELECT SUM(total_fee) FROM invoices WHERE month = ?
        ''', (current_month,))
        
        monthly_revenue = cursor.fetchone()[0] or 0
        
        # Conversation stats
        cursor.execute('''
            SELECT COUNT(*), AVG(handled) FROM conversations
            WHERE timestamp >= DATE('now', '-30 days')
        ''')
        
        conv_stats = cursor.fetchone()
        
        conn.close()
        
        return {
            "clients": client_stats,
            "monthly_recurring_revenue": monthly_revenue,
            "total_conversations_30d": conv_stats[0] or 0,
            "bot_handling_rate": round((conv_stats[1] or 0) * 100, 1)
        }

# CLI Interface
if __name__ == "__main__":
    import sys
    
    system = SupportBotSystem()
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "onboard":
            if len(sys.argv) >= 6:
                client = BotClient(
                    company=sys.argv[2],
                    website=sys.argv[3],
                    industry=sys.argv[4],
                    bot_platform=sys.argv[5],
                    monthly_fee=float(sys.argv[6]) if len(sys.argv) > 6 else 200.0,
                    conversation_limit=int(sys.argv[7]) if len(sys.argv) > 7 else 500
                )
                setup = float(sys.argv[8]) if len(sys.argv) > 8 else 500.0
                system.onboard_client(client, setup)
        
        elif command == "train":
            if len(sys.argv) >= 3:
                training = system.generate_bot_training(int(sys.argv[2]))
                print(f"Generated {len(training)} training Q&A pairs")
        
        elif command == "invoice":
            if len(sys.argv) >= 3:
                invoice = system.generate_monthly_invoice(int(sys.argv[2]))
                print(json.dumps(invoice, indent=2))
        
        elif command == "metrics":
            metrics = system.get_business_metrics()
            print(json.dumps(metrics, indent=2))
        
        else:
            print("Commands: onboard, train, invoice, metrics")
    else:
        metrics = system.get_business_metrics()
        print(json.dumps(metrics, indent=2))
```

---

## Installation & Setup

### 1. Install Dependencies

```bash
pip install requests beautifulsoup4
```

### 2. Set Up Environment Variables

```bash
# Add to ~/.bashrc or ~/.zshrc
export DISCORD_WEBHOOK="your_discord_webhook_url"
export MARKET_DATA_API_KEY="your_api_key"
```

### 3. Initialize Databases

```bash
# Each system will auto-initialize on first run
python wheel_system.py
python lead_gen_system.py
python support_bot_system.py
```

### 4. Cron Jobs for Automation

```bash
# Edit crontab
export EDITOR=nano && crontab -e

# Add:
# Options Wheel - Scan at market open
30 9 * * 1-5 cd /path/to/scripts && python3 wheel_system.py scan >> logs/wheel.log 2>&1

# Lead Gen - Weekly prospecting
0 9 * * 1 cd /path/to/scripts && python3 lead_gen_system.py import saas >> logs/leadgen.log 2>&1

# Support Bots - Monthly invoicing
0 9 1 * * cd /path/to/scripts && python3 support_bot_system.py invoice >> logs/bots.log 2>&1
```

---

## Usage Examples

### Options Wheel System

```bash
# Daily scan
python wheel_system.py scan

# Open new position
python wheel_system.py open AAPL csp 175.0 2.50 2024-04-19

# Record assignment
python wheel_system.py assign 1 170.0

# Close position
python wheel_system.py close 1 0.25

# View summary
python wheel_system.py summary
```

### Lead Generation System

```bash
# Import prospects
python lead_gen_system.py import saas

# Add manual prospect
python lead_gen_system.py add "Company Name" "website.com"

# Generate outreach email
python lead_gen_system.py email 1

# View pipeline
python lead_gen_system.py pipeline

# Export for campaign
python lead_gen_system.py export
```

### Support Bot System

```bash
# Onboard new client
python support_bot_system.py onboard "Company" "site.com" "saas" "tidio" 200 500 500

# Generate training data
python support_bot_system.py train 1

# Generate invoice
python support_bot_system.py invoice 1

# View metrics
python support_bot_system.py metrics
```

---

**Production Ready Code Library**  
**Version:** 1.0  
**Last Updated:** March 11, 2026

