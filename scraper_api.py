from fastapi import FastAPI
from pydantic import BaseModel
from amazon_scraper import AmazonScraperService

app = FastAPI()
scraper = AmazonScraperService()

class ScrapeRequest(BaseModel):
    asin_or_url: str

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/scrape")
async def scrape(req: ScrapeRequest):
    try:
        result = scraper.scrape_amazon_product(req.asin_or_url)
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "error": str(e)}
