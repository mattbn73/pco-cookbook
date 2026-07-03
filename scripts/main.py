import os, sys, requests
from pathlib import Path
from dotenv import load_dotenv
SECRETS = Path.home() / "Secrets" / "pco.env"
if not SECRETS.exists(): sys.exit("No secrets file")
load_dotenv(dotenv_path=SECRETS)
cid = os.getenv("PCO_CLIENT_ID")
sec = os.getenv("PCO_SECRET")
if not cid or not sec: sys.exit("Missing creds")
print("Client ID:", cid[:4] + "...", "length", len(cid))
print("Secret length:", len(sec))
URL = "https://api.planningcenteronline.com/services/v2/"
r = requests.get(URL, auth=(cid, sec))
print("GET", URL)
print("Status:", r.status_code)
print(r.text)
