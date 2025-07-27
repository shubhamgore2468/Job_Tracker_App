import os
import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from typing import Optional
from datetime import datetime
from utils import fetch_dynamic_content
from logger import logger
from utils import extract_job_data, clean_job_data, add_to_notion
from models import JobScrapeRequest, JobData, FIELD_MAP
from notion_client import Client


load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
RESUME_LINK = os.getenv("RESUME_LINK")

notion = Client(auth=os.getenv("NOTION_TOKEN"))


logger.info(f"Using Notion DB ID: {NOTION_DATABASE_ID}")
logger.info(f"Using Notion Token length: {len(NOTION_TOKEN) if NOTION_TOKEN else 'None'}, NOTION_TOKEN: {NOTION_TOKEN}")


app = FastAPI(title="Job Tracker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post('/scrape-job')
async def scrape_job(request: JobScrapeRequest, background_tasks: BackgroundTasks):
    """Scrape job details from a given URL and save to Notion."""
    logger.info(f"Received request to scrape job from URL: {request.url}")
    try:

        # if request.page_content:
        #     content = request.page_content
        #     logger.info("Using provided page content.")
        # else:
        content = await fetch_dynamic_content(str(request.url))
        logger.info("Fetched dynamic content using Playwright.")

        
        job_data = await extract_job_data(content, str(request.url))
        
        logger.info(f"Extracted job data: {job_data}")
        clean_job_data(job_data)
        background_tasks.add_task(add_to_notion, job_data)
        logger.info("Background task to add job to Notion has been scheduled.")

        return {
            "status": "success",
            # "job_data": job_data,
            "message": "Job scraped and being added to Notion"
        }
    except httpx.HTTPError as e:
        logger.error(f"Error fetching page: {e}")
        raise HTTPException(status_code=400, detail="Failed to fetch job page.")
    except Exception as e:
        logger.exception("Unexpected error in scrape-job endpoint")
        raise HTTPException(status_code=500, detail=str(e))


@app.get('/hello_world')
async def hello_world():
    """Simple endpoint to check if the API is running."""
    return {"message": "Hello, World!"}

@app.get('/health')
async def health_check():
    if not NOTION_TOKEN or not NOTION_DATABASE_ID:
        logger.error("NOTION_TOKEN or NOTION_DATABASE_ID not set in environment.")
        return ""

    notion = Client(auth=NOTION_TOKEN)

    try:
        logger.info(f"Checking access to Notion database ID: {NOTION_DATABASE_ID}")
        response = notion.databases.retrieve(NOTION_DATABASE_ID)
        print(response)
        logger.info("Successfully accessed the database!")
        logger.info(f"Database title: {response['title'][0]['plain_text']}")
        return {"status":"healthy"}
    except Exception as e:
        logger.error(f"Failed to access Notion database: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)