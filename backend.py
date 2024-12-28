import warnings
from fastapi import FastAPI, HTTPException, Query
from elasticsearch import Elasticsearch
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware


ingredients_list = [
    "Vitamin B1 (Thiamine)", "Vitamin B2 (Riboflavin)", "Vitamin B3 (Niacin)",
    "Vitamin B5 (Pantothenic Acid)", "Vitamin B6 (Pyridoxine)", "Vitamin B7 (Biotin)",
    "Vitamin B9 (Folate/Folic Acid)", "Vitamin B12 (Cobalamin)", "Vitamin C (Ascorbic Acid)",
    "Vitamin A (Retinol, Beta-Carotene)", "Vitamin D (Cholecalciferol, Ergocalciferol)",
    "Vitamin E (Tocopherols, Tocotrienols)", "Vitamin K (Phylloquinone, Menaquinones)",
    "Choline", "Inositol", "Carnitine", "PABA (Para-Aminobenzoic Acid)",
    "Coenzyme Q10 (Ubiquinone)"
]

warnings.filterwarnings("ignore", category=UserWarning)

es = Elasticsearch(
    "http://localhost:9200"  # No need for HTTPS
)

print(es.info())


app = FastAPI()

# Correctly mount the "static" folder
app.mount("/static", StaticFiles(directory="D:/IASBS/Abott/fastAPI/static", html=True), name="static")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins. Use specific domains for production.
    allow_credentials=True,
    allow_methods=["*"],  # Allows all HTTP methods.
    allow_headers=["*"],  # Allows all headers.
)

# Data model for ingredient
class Ingredient(BaseModel):
    name: str
    stability_info: str
    references: list[str]

# Function to fetch data from PubMed
def fetch_pubmed(ingredient):
    url = f"https://pubmed.ncbi.nlm.nih.gov/?term={ingredient}"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')

    results = []
    for article in soup.find_all('article', class_='full-docsum'):
        title = article.find('a', class_='docsum-title').text.strip()
        link = "https://pubmed.ncbi.nlm.nih.gov" + article.find('a')['href']
        results.append({"title": title, "url": link})

    return results




@app.post("/fetch_and_index_all/")
async def fetch_and_index_all():
    results = []
    for ingredient in ingredients_list:
        print(f"Fetching data for: {ingredient}")  # Log the current ingredient

        try:
            # Fetch data from PubMed
            pubmed_data = fetch_pubmed(ingredient)
            print(f"PubMed data for {ingredient}: {pubmed_data}")  # Log the fetched data

            stability_info = f"Stability information for {ingredient} fetched from PubMed."
            references = [entry['url'] for entry in pubmed_data]

            # Create document
            document = {
                "name": ingredient,
                "stability_info": stability_info,
                "references": references
            }
            print(f"Document for {ingredient}: {document}")  # Log the document to be indexed

            # Index document in Elasticsearch
            response = es.index(index="ingredients", document=document)
            results.append({"ingredient": ingredient, "id": response["_id"], "result": response["result"]})
        except Exception as e:
            print(f"Error processing {ingredient}: {e}")  # Log the error
            results.append({"ingredient": ingredient, "error": str(e)})

    return results


# Endpoint to add ingredient data
@app.post("/ingredients/")
async def add_ingredient(ingredient: Ingredient):
    document = ingredient.dict()
    response = es.index(index="ingredients", document=document)
    return {"id": response["_id"], "result": response["result"]}


# Endpoint to search for an ingredient
@app.get("/search/")
async def search_ingredient(name: str = Query(...)):
    query = {
        "query": {
            "match": {
                "name": name
            }
        }
    }
    response = es.search(index="ingredients", body=query)
    hits = response.get("hits", {}).get("hits", [])

    if not hits:
        raise HTTPException(status_code=404, detail="Ingredient not found")

    # Extract the first unique result for the searched ingredient
    unique_results = {}
    for hit in hits:
        ingredient_name = hit["_source"]["name"]
        if ingredient_name not in unique_results:
            unique_results[ingredient_name] = hit["_source"]

    # Return the first unique result
    return list(unique_results.values())


# Endpoint to fetch and index PubMed data
@app.post("/fetch_and_index/")
async def fetch_and_index(ingredient_name: str):
    pubmed_data = fetch_pubmed(ingredient_name)
    stability_info = (
        f"The stability of {ingredient_name} is summarized based on "
        f"{len(pubmed_data)} PubMed articles. This includes factors like storage conditions, "
        "temperature effects, and pH stability. Refer to the links below for more details."
    )
    references = [entry['url'] for entry in pubmed_data]

    document = {
        "name": ingredient_name,
        "stability_info": stability_info,
        "references": references
    }

    response = es.index(index="ingredients", document=document)
    return {"id": response["_id"], "result": response["result"]}
