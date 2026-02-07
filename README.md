# ilboursa Stock Scraper with MongoDB

Complete Docker setup to scrape stock data from ilboursa.com and store in MongoDB.

## 📁 Structure
.
├── docker-compose.yml              # One-time scrape setup
├── docker-compose.scheduled.yml  # Automated hourly scraping
├── scraper/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── scraper.py


## 🚀 Quick Start

### 1. One-time Scrape
```bash
docker-compose up --build
```
This will:
- Start MongoDB on port 27017
- Run scraper once
- Save data to MongoDB
- Start MongoDB Express on http://localhost:8081
### 2. Scheduled Scraping (every hour)
```
docker-compose -f docker-compose.scheduled.yml up --build -d
```
### 3. View Data
- MongoDB Express: http://localhost:8081 (user: user, pass: pass)
- Connect via MongoDB Compass: mongodb://admin:password123@localhost:27017/

## 🔧 Configuration
MongoDB Credentials
- Root Username: admin
- Root Password: password123
- Database: ilboursa_db
- Collection: stocks
Data Schema
```
{
  "title": "AETECH",
  "code": "AETEC",
  "consensus": "60,33 DT",
  "potential": "+7.74%",
  "scraped_at": "2024-01-15T10:30:00Z"
}
```
