from pydantic import HttpUrl, BaseModel
from typing import Optional, List
from datetime import datetime

class JobScrapeRequest(BaseModel):
    url: HttpUrl
    page_content: Optional[str] = None

class JobData(BaseModel):
    title: str
    company: str
    location: Optional[str] = None
    description: Optional[str] = None
    salary: Optional[str] = None
    job_type: Optional[str] = None      
    experience_level: Optional[str] = None 
    url: str
    scraped_at: datetime
    status: Optional[str] = None
    resume: Optional[str] = None


FIELD_MAP = {
    "Company": "company",
    "Role": "title",
    "Location": "location",
    "Flexibility": "job_type",
    "Category": "experience_level",
    "Status": "status",            # optional if your model allows
    "Applied Date": "applied_date",  # optional if used
    "Link": "url",
    "Resume": "resume"
}