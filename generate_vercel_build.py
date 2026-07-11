import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configure encoding for Windows console output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# Import scrapers from Flask backend app
try:
    from app import scrape_samsa, scrape_spacio, scrape_vimora, scrape_mmpp, scrape_fabricadevelas, agrupar_productos
except ImportError as e:
    print("Error importing app modules. Ensure app.py exists in the same directory:", e)
    sys.exit(1)

def main():
    print("====================================================")
    print("Todo Insumos - Static Catalog Compiler for Vercel")
    print("====================================================")
    
    results = []
    
    scrapers = {
        "Samsa Aromas": scrape_samsa,
        "Spacio Natural": scrape_spacio,
        "Vimora Natural": scrape_vimora,
        "MMPP": scrape_mmpp,
        "Fábrica de Velas": scrape_fabricadevelas
    }
    
    print("Crawling and parsing all 5 suppliers in parallel...")
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(func): name for name, func in scrapers.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                prods = future.result()
                print(f" -> {name}: Extracted {len(prods)} variants.")
                results.extend(prods)
            except Exception as e:
                print(f" -> {name}: FAILED to crawl: {e}")
                
    print(f"\nTotal raw variants harvested: {len(results)}")
    
    print("Grouping and standardizing names (BPF/APF) and filtering foods...")
    grouped = agrupar_productos(results)
    print(f"Total unique consolidated products: {len(grouped)}")
    
    # Read templates/index.html
    template_path = os.path.join("templates", "index.html")
    if not os.path.exists(template_path):
        print(f"Error: Template file not found at {template_path}")
        sys.exit(1)
        
    with open(template_path, "r", encoding="utf-8") as f:
        html_template = f.read()
        
    # Inject compiled JSON into JavaScript catalog placeholder
    catalog_json = json.dumps(grouped, ensure_ascii=False)
    html_compiled = html_template.replace("/* STATIC_CATALOG_PLACEHOLDER_JSON */", catalog_json)
    
    # Save self-contained index.html at root
    output_path = "index.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_compiled)
        
    print("====================================================")
    print(f"SUCCESS: Compiled static file saved to: {os.path.abspath(output_path)}")
    print("You can now push this workspace to GitHub and deploy it directly on Vercel!")
    print("====================================================")

if __name__ == "__main__":
    main()
