from playwright.async_api import async_playwright
import asyncio
from models import JobData, FIELD_MAP
from datetime import datetime, timezone
import re
from logger import logger
import openai
from notion_client import Client
import os
from dotenv import load_dotenv
import json
from bs4 import BeautifulSoup
from typing import Union, Optional

# The client gets the API key from the environment variable `GEMINI_API_KEY`.

load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
RESUME_LINK = os.getenv("RESUME_LINK")

notion = Client(auth=os.getenv("NOTION_TOKEN"))
OpenAI_client = openai.OpenAI(api_key=OPENAI_API_KEY)

async def fetch_dynamic_content(url: str) -> str:

    """Fetch dynamic content using Playwright with popup handling"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            # Block common tracking and ads
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        
        # Block unnecessary resources to speed up loading
        await context.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "stylesheet", "font", "media"] else route.continue_())
        
        page = await context.new_page()
        
        try:
            # Navigate to the page
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            
            # Handle common cookie/privacy popups
            popup_selectors = [
                # Common cookie banner selectors
                'button[id*="accept"]',
                'button[class*="accept"]',
                'button[aria-label*="accept"]',
                'button:has-text("Accept")',
                'button:has-text("Accept All")',
                'button:has-text("Accept Cookies")',
                'button:has-text("OK")',
                'button:has-text("Got it")',
                'button:has-text("I Agree")',
                'button:has-text("Continue")',
                
                # Close buttons for popups
                'button[aria-label*="close"]',
                'button[class*="close"]',
                '[class*="modal"] button',
                '[class*="popup"] button',
                '.cookie-banner button',
                '#cookie-banner button',
                
                # Privacy policy related
                'button:has-text("Privacy Policy")',
                'button:has-text("Decline")',
            ]
            
            # Try to close popups
            for selector in popup_selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=2000)
                    if element:
                        await element.click()
                        await page.wait_for_timeout(1000)  # Wait for popup to close
                        break
                except:
                    continue
            
            # Wait a bit more for content to load
            await page.wait_for_timeout(3000)
            
            # Get the page content
            content = await page.content()
            return content
            
        except Exception as e:
            print(f"Error fetching content: {e}")
            # Fallback: try to get content anyway
            try:
                content = await page.content()
                return content
            except:
                return ""
        finally:
            await browser.close()


def normalize_fields(raw: dict, url: str) -> dict:
    job_data = {}
    for key, value in raw.items():
        mapped_key = FIELD_MAP.get(key)
        if mapped_key:
            job_data[mapped_key] = value
    job_data["url"] = url
    job_data["scraped_at"] = datetime.now()
    job_data.setdefault("requirements", [])
    job_data.setdefault("benefits", [])
    return job_data

def clean_job_data(job_data: JobData) -> JobData:
    """Clean and normalize job data."""
    job_dict = job_data.dict()

    for field_name, field_value in job_dict.items():
        if isinstance(field_value, str) and field_value:
            cleaned_value = re.sub(r'[^\w\s\-\.,!?]', '', field_value)
            job_dict[field_name] = cleaned_value.strip()
            setattr(job_data, field_name, cleaned_value.strip())
    return job_data

def convert_all_values_to_strings(d: dict) -> dict:
    new_dict = {}
    for k, v in d.items():
        if isinstance(v, list):
            # Join list items as comma-separated strings
            new_dict[k] = ", ".join(str(i) for i in v)
        elif v is None:
            new_dict[k] = ""
        else:
            new_dict[k] = str(v)
    return new_dict


async def extract_job_data(html_content: str, url: str) -> JobData:
    """Extract structured job data using AI"""

    schema_fields = [
        "Company",
        "Role",
        "Category",
        "Location",
        "Flexibility",
        "Status",
        "Applied Date",
        "Link",
        "Resume",
    ]

    fields_str = ", ".join(schema_fields)

    logger.info(f"Starting job data extraction for URL: {url}")
    soup = BeautifulSoup(html_content, 'html.parser')
    body = soup.body
    text_content = body.get_text(separator='\n', strip=True) if body else ""

    # if len(text_content) > 8000:
    #     logger.info("Truncating page content to fit token limit")
    #     text_content = text_content[:8000]
    

    print('text_content - -')
    print('_'*50)
    print(text_content)
    print('_'*50)

    prompt = f"""
                Extract job data from this posting:

                {text_content[:8000]}

                Please output a JSON object with the following keys ONLY:
                {fields_str}

                If any field is missing, omit it from the JSON.

                URL: {url}
            """

    try:
        logger.info("Calling OpenAI API for job extraction")
        
        response = OpenAI_client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )


        logger.info("OpenAI response received successfully")
        
        raw_response = json.loads(response.choices[0].message.content)
        print('_'*50)
        print(raw_response)
        print('_'*50)
        job_info = normalize_fields(raw_response, url)
        job_info['scraped_at'] = datetime.now()

        job_info = convert_all_values_to_strings(job_info)

        return JobData(**job_info)

    except Exception as e:
        logger.exception("Failed to extract job data from OpenAI response")
        raise RuntimeError("OpenAI parsing or request failed.")

def clean_select_value(value: Optional[str]) -> Optional[str]:
    return value.replace(",", " /").strip() if value else None

def clean_text_value(value: Union[str, list, None]) -> str:
    if isinstance(value, list):
        return ", ".join(str(v) for v in value if v).strip()
    if isinstance(value, str):
        return value.strip()
    return ""

async def add_to_notion(job_data: JobData):
    """Add job data to Notion database, and create properties if they don't exist."""
    logger.info(f"Adding job '{job_data.title}' at '{job_data.company}' to Notion.")

    try:
        # 1. Get current database properties
        db_info = notion.databases.retrieve(database_id=NOTION_DATABASE_ID)
        current_properties = db_info["properties"]

        # 2. Define required properties and their types
        required_fields = {
            "Company": {"type": "title"},
            "Role": {"type": "rich_text"},
            "Location": {"type": "rich_text"},
            "Category": {"type": "select"},
            "Flexibility": {"type": "select"},
            "Status": {"type": "select"},
            "Applied Date": {"type": "date"},
            "Link": {"type": "url"},
            "Resume": {"type": "files"},
        }

        # 3. Add missing fields
        for field_name, field_config in required_fields.items():
            if field_name not in current_properties:
                logger.info(f"Creating missing property: {field_name}")
                notion.databases.update(
                    database_id=NOTION_DATABASE_ID,
                    properties={
                        field_name: field_config
                    }
                )

        # 4. Build properties dict for the new job page
        properties = {
            "Company": {
                "title": [{"text": {"content": clean_text_value(job_data.company)}}]
            },
            "Role": {
                "rich_text": [{"text": {"content": clean_text_value(job_data.title)}}]
            },
            "Location": {
                "rich_text": [{
                    "text": {"content": clean_text_value(job_data.location)}
                }]
            },
            "Category": {
                "select": {
                    "name": clean_select_value(job_data.experience_level)
                } if job_data.experience_level else None
            },
            "Flexibility": {
                "select": {
                    "name": clean_select_value(job_data.job_type)
                } if job_data.job_type else None
            },
            "Status": {
                "select": {"name": "Applied"}
            },
            "Applied Date": {
                "date": {
                    "start": datetime.now(timezone.utc).isoformat()
                }
            },
            "Link": {
                "url": clean_text_value(job_data.url)
            }
        }

        # 5. Add resume if available
        if RESUME_LINK:
            properties["Resume"] = {
                "files": [
                    {
                        "type": "external",
                        "name": "Resume",
                        "external": {"url": RESUME_LINK}
                    }
                ]
            }
        print('_'*50)    
        print(job_data)
        print('_'*50)
        # 6. Create page
        notion.pages.create(
            parent={"database_id": NOTION_DATABASE_ID},
            properties=properties,
        )

        logger.info("Job successfully added to Notion.")

    except Exception as e:
        logger.exception(" Failed to add job to Notion")            