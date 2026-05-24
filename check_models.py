from groq import Groq
import os
from dotenv import load_dotenv

load_dotenv()
c = Groq(api_key=os.getenv('ROAST3'))
models = c.models.list()
for m in models.data:
    print(m.id)
