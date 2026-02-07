#!/usr/bin/env python3
"""
ilboursa Complete Stock Scraper
- Scrapes company list from synthese_fiches
- For each company, scrapes shareholders and financial data
- Stores all in MongoDB with company code as foreign key
"""

import requests
from bs4 import BeautifulSoup
from pymongo import MongoClient
from datetime import datetime
import logging
import sys
import os
import time
import random

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# MongoDB connection settings
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://admin:password123@mongo:27017/ilboursa_db?authSource=admin')
DB_NAME = "ilboursa_db"

class IlboursaScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        })
        self.base_url = "https://www.ilboursa.com"
        self.client = None
        self.db = None
        
    def connect_mongodb(self):
        """Connect to MongoDB"""
        try:
            self.client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
            self.client.admin.command('ping')
            self.db = self.client[DB_NAME]
            logger.info("✅ Connected to MongoDB")
            
            # Create indexes
            self.db.companies.create_index('code', unique=True)
            self.db.shareholders.create_index([('company_code', 1), ('name', 1)], unique=True)
            self.db.financials.create_index([('company_code', 1), ('metric', 1)], unique=True)
            
            return True
        except Exception as e:
            logger.error(f"❌ MongoDB connection failed: {e}")
            return False
    
    def get_company_list(self):
        """Get list of all companies from synthese_fiches"""
        url = f"{self.base_url}/analyses/synthese_fiches"
        logger.info(f"📋 Fetching company list from {url}")
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            table = soup.find('table', id='tabQuotes')
            
            if not table:
                logger.error("Company list table not found")
                return []
            
            companies = []
            tbody = table.find('tbody')
            if tbody:
                for row in tbody.find_all('tr'):
                    td = row.find('td')
                    if td:
                        a_tag = td.find('a')
                        if a_tag:
                            href = a_tag.get('href', '')
                            code = href.split('/')[-1] if '/' in href else href
                            title = a_tag.get_text(strip=True)
                            
                            # Get consensus and potential from summary page
                            tds = row.find_all('td')
                            consensus = tds[1].get_text(strip=True) if len(tds) > 1 else ""
                            potential = tds[2].get_text(strip=True) if len(tds) > 2 else ""
                            
                            companies.append({
                                'code': code,
                                'title': title,
                                'consensus': consensus,
                                'potential': potential,
                                'url': f"{self.base_url}/marches/societe/{code}",
                                'scraped_at': datetime.utcnow()
                            })
            
            logger.info(f"📊 Found {len(companies)} companies")
            return companies
            
        except Exception as e:
            logger.error(f"Failed to get company list: {e}")
            return []
    
    def scrape_shareholders(self, company_code, company_url):
        """Scrape shareholders for a specific company"""
        logger.info(f"👥 Scraping shareholders for {company_code}")
        
        try:
            response = self.session.get(company_url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            table = soup.find('table', id='tblactions')
            
            shareholders = []
            if table:
                tbody = table.find('tbody')
                if tbody:
                    for row in tbody.find_all('tr'):
                        tds = row.find_all('td')
                        if len(tds) >= 3:
                            # Color box (td[0]), Name (td[1]), Percentage (td[2])
                            name = tds[1].get_text(strip=True)
                            percentage = tds[2].get_text(strip=True)
                            
                            if name and percentage:
                                shareholders.append({
                                    'company_code': company_code,
                                    'name': name,
                                    'percentage': percentage,
                                    'scraped_at': datetime.utcnow()
                                })
            
            logger.info(f"  └─ Found {len(shareholders)} shareholders")
            return shareholders
            
        except Exception as e:
            logger.error(f"  └─ Error scraping shareholders: {e}")
            return []
    
    def scrape_financials(self, company_code, company_url):
        """Scrape financial data for a specific company"""
        logger.info(f"💰 Scraping financials for {company_code}")
        
        try:
            response = self.session.get(company_url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            table = soup.find('table', class_='tablenosort tbl100_6 tabSociete')
            
            financials = []
            if table:
                # Get years from header
                thead = table.find('thead')
                years = []
                if thead:
                    header_cells = thead.find_all('th')[1:]  # Skip first empty th
                    years = [cell.get_text(strip=True) for cell in header_cells]
                
                # Get data rows
                tbody = table.find('tbody')
                if tbody and years:
                    for row in tbody.find_all('tr'):
                        cells = row.find_all('td')
                        if len(cells) > 0:
                            metric_name = cells[0].get_text(strip=True)
                            values = {}
                            
                            for i, cell in enumerate(cells[1:]):
                                if i < len(years):
                                    year = years[i]
                                    value = cell.get_text(strip=True)
                                    if value and value != '-':
                                        values[year] = value
                            
                            if values:
                                financials.append({
                                    'company_code': company_code,
                                    'metric': metric_name,
                                    'values': values,
                                    'scraped_at': datetime.utcnow()
                                })
            
            logger.info(f"  └─ Found {len(financials)} financial metrics")
            return financials
            
        except Exception as e:
            logger.error(f"  └─ Error scraping financials: {e}")
            return []
    
    def save_companies(self, companies):
        """Save companies to MongoDB"""
        if not companies:
            return
        
        collection = self.db.companies
        inserted = 0
        updated = 0
        
        for company in companies:
            result = collection.update_one(
                {'code': company['code']},
                {'$set': company},
                upsert=True
            )
            if result.upserted_id:
                inserted += 1
            elif result.modified_count:
                updated += 1
        
        logger.info(f"💾 Companies: {inserted} inserted, {updated} updated")
    
    def save_shareholders(self, shareholders):
        """Save shareholders to MongoDB"""
        if not shareholders:
            return
        
        collection = self.db.shareholders
        inserted = 0
        updated = 0
        
        for sh in shareholders:
            result = collection.update_one(
                {'company_code': sh['company_code'], 'name': sh['name']},
                {'$set': sh},
                upsert=True
            )
            if result.upserted_id:
                inserted += 1
            elif result.modified_count:
                updated += 1
        
        logger.info(f"💾 Shareholders: {inserted} inserted, {updated} updated")
    
    def save_financials(self, financials):
        """Save financials to MongoDB"""
        if not financials:
            return
        
        collection = self.db.financials
        inserted = 0
        updated = 0
        
        for fin in financials:
            result = collection.update_one(
                {'company_code': fin['company_code'], 'metric': fin['metric']},
                {'$set': fin},
                upsert=True
            )
            if result.upserted_id:
                inserted += 1
            elif result.modified_count:
                updated += 1
        
        logger.info(f"💾 Financials: {inserted} inserted, {updated} updated")
    
    def run(self):
        """Main execution flow"""
        logger.info("🚀 Starting complete ilboursa scraping...")
        
        # Connect to MongoDB
        if not self.connect_mongodb():
            return False
        
        # Get company list
        companies = self.get_company_list()
        if not companies:
            logger.error("No companies found")
            return False
        
        # Save companies first
        self.save_companies(companies)
        
        # Scrape details for each company
        total = len(companies)
        for i, company in enumerate(companies, 1):
            code = company['code']
            url = company['url']
            
            logger.info(f"\n[{i}/{total}] Processing {code} - {company['title']}")
            
            # Scrape shareholders
            shareholders = self.scrape_shareholders(code, url)
            self.save_shareholders(shareholders)
            
            # Scrape financials
            financials = self.scrape_financials(code, url)
            self.save_financials(financials)
            
            # Be nice to the server
            if i < total:
                sleep_time = random.uniform(1, 3)
                logger.info(f"⏳ Sleeping {sleep_time:.1f}s before next company...")
                time.sleep(sleep_time)
        
        # Summary
        logger.info("\n" + "="*50)
        logger.info("📊 SCRAPING SUMMARY")
        logger.info("="*50)
        logger.info(f"Companies: {self.db.companies.count_documents({})}")
        logger.info(f"Shareholders: {self.db.shareholders.count_documents({})}")
        logger.info(f"Financial records: {self.db.financials.count_documents({})}")
        logger.info("="*50)
        
        self.client.close()
        logger.info("✅ Scraping completed!")
        return True

def main():
    scraper = IlboursaScraper()
    success = scraper.run()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()