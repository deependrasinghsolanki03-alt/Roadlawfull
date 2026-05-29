import os
import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
url = f"{SUPABASE_URL}/storage/v1/object/public/legal-pdfs/India.pdf"
res = requests.head(url)
print(res.status_code)
print(res.headers)
