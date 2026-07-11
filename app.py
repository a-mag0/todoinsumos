from flask import Flask, render_template, jsonify
import requests
from bs4 import BeautifulSoup
import re
import sys
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configure UTF-8 encoding on Windows to prevent output errors
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

app = Flask(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"
}
TIMEOUT = 15

def normalize_size(size_str):
    if not size_str:
        return "Otro"
    size_str = size_str.lower().strip()
    
    # 20 Kg
    if any(k in size_str for k in ['20 kg', '20kg', '20 kilo', '20kilo']):
        return "20 Kg"
    # 10 Kg
    if any(k in size_str for k in ['10 kg', '10kg', '10 kilo', '10kilo']):
        return "10 Kg"
    # 5 Litros / Kg
    if any(k in size_str for k in ['5 litro', '5 l', '5 kg', '5kg', '5000', '5 kilo', '5000 ml', '5000 cc', '5kilos']):
        return "5 L / 5 Kg"
    # 1 Litro / Kg
    if any(k in size_str for k in ['1 litro', '1 l', '1 kg', '1kg', '1000', '1 kilo', '1000 ml', '1000 ml/g', '1000cc', '1000 cc', '1kilo', '1 k', '1k']):
        return "1 L / 1 Kg"
    # 500 ml / g
    if any(k in size_str for k in ['500 ml', '500ml', '500 gr', '500g', '500gr', '500 g', '1/2 kilo', 'medio kilo']):
        return "500 ml/g"
    # 250 ml / g
    if any(k in size_str for k in ['250 ml', '250ml', '250 gr', '250g', '250gr', '250 g']):
        return "250 ml/g"
    # 100 ml / g
    if any(k in size_str for k in ['100 ml', '100ml', '100 gr', '100g', '100gr', '100 grs', '100grs', '100 g']):
        return "100 ml/g"
    # 30 ml / g
    if any(k in size_str for k in ['30 ml', '30ml', '30 gr', '30g', '30gr', '30 g']):
        return "30 ml/g"
    # 15-20 gr
    if any(k in size_str for k in ['15 gr', '15g', '15gr', '20 gr', '20g', '20gr', '15 g', '20 g']):
        return "15-20 g"
        
    return size_str

def normalize_product_name(name):
    if not name:
        return ""
    name_norm = name.lower()
    
    # Remove accents
    name_norm = name_norm.replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u')
    
    # Standardize soy wax fusion points
    fusion = ""
    if any(k in name_norm for k in ['bajo punto de fusion', 'bpf', 'b.p.f.', 'punto de fusion bajo']):
        fusion = " BPF"
    elif any(k in name_norm for k in ['alto punto de fusion', 'apf', 'a.p.f.', 'punto de fusion alto', 'punto de fusion 62', 'punto de  fusion 62']):
        # Standardize Punto de Fusion 62 as APF
        fusion = " APF"
        
    # Standardize Soy Wax
    if 'cera' in name_norm and ('soja' in name_norm or 'soya' in name_norm):
        return f"Cera de Soja{fusion}"
        
    # Standardize Beeswax
    if 'cera' in name_norm and ('abeja' in name_norm or 'abejas' in name_norm):
        return "Cera de Abeja"
        
    # Standardize Arena Perlada
    if 'arena perl' in name_norm or 'cera arena' in name_norm:
        return "Cera Arena Perlada"
        
    # Remove sizes and format identifiers from name
    name_norm = re.sub(r'\b\d+\s*(ml|gr|g|kg|l|cc|kilo|litro)s?\b', '', name_norm)
    name_norm = re.sub(r'\b(aceite de|aceite esencial|aceite|esencia de|esencia|aroma|velas y jabones|insumos|fragancia|fragancias)\b', '', name_norm)
    name_norm = re.sub(r'^\d+\s*-\s*', '', name_norm)
    name_norm = re.sub(r'\s+', ' ', name_norm).strip(" –-")
    
    # Standardize common products
    if name_norm == 'coco':
        return "Aceite de Coco"
    if name_norm == 'jojoba':
        return "Aceite de Jojoba"
    if name_norm == 'almendra' or name_norm == 'almendras':
        return "Aceite de Almendras"
        
    return name_norm.title()

def classify_and_clean_product(norm_name, provider):
    name_lower = norm_name.lower()
    
    # Exclude irrelevant products (food ingredients and general accessories)
    exclude_words = [
        'etiqueta', 'instrucciones', 'modo de uso', 'caja', 'bolsa', 'envase', 'servicio', 'curso', 'despacho', 
        'pack 3 aromas', 'pack de aromas', 'carne de soya', 'carne de soja', 'poroto', 'lenteja', 'garbanzo', 
        'chia', 'avena', 'quinoa', 'sal de mar', 'sal de maras', 'sal de cahuil', 'arroz', 'harina', 'nuez', 
        'almendras tostadas', 'coco rallado', 'mani', 'semilla', 'oregano', 'pimienta', 'comino', 'aliño',
        'cesta', 'bolsita', 'cajita'
    ]
    if any(ew in name_lower for ew in exclude_words):
        return None
        
    if provider == "Samsa Aromas":
        return "Fragancias"
        
    # Ceras category
    if any(w in name_lower for w in ['cera', 'soja', 'soya', 'abeja', 'parafina', 'arena perlada', 'vaselina']):
        return 'Ceras'
        
    # Moldes category
    if any(w in name_lower for w in ['molde', 'silicona', 'shapes']):
        return 'Moldes'
        
    # Aceites y Materias Primas category
    if any(w in name_lower for w in ['aceite', 'manteca', 'jojoba', 'almendra', 'pepita', 'rosa mosqueta', 'coco', 'glicerina', 'aditivo', 'colorante', 'acido citrico', 'bicarbonato', 'agua de rosas', 'btms', 'sci', 'carbon', 'pabilo', 'mecha', 'ojetillo', 'estearina', 'mica', 'soporte']):
        return 'Aceites y Materias Primas'
        
    # Fallback category
    return 'Fragancias'

# Samsa Aromas collection scraper
def scrape_samsa_collection(col_name):
    url = f"https://samsaaromas.com/collections/{col_name}/products.json?limit=250"
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    if r.status_code != 200:
        return []
    data = r.json()
    products = []
    for p in data.get("products", []):
        name = p.get("title")
        variants = p.get("variants", [])
        img_url = p.get("images")[0].get("src") if p.get("images") else None
        for v in variants:
            v_title = v.get("title")
            price_str = str(v.get("price"))
            # Extract digits to make it an integer
            digits = "".join(re.findall(r'\d+', price_str))
            price = int(digits) if digits else None
            if v_title and price is not None:
                products.append({
                    "provider": "Samsa Aromas",
                    "product_name": name,
                    "title": v_title,
                    "price": price,
                    "url": f"https://samsaaromas.com/products/{p.get('handle')}",
                    "image_url": img_url
                })
    return products

def scrape_samsa():
    results = []
    results.extend(scrape_samsa_collection("aromas"))
    results.extend(scrape_samsa_collection("insumos"))
    return results

# Spacio Natural detail scraper
def extract_spacio_price_dynamic(item, data):
    for k, v in item.items():
        if isinstance(v, int) and 0 <= v < len(data):
            val_obj = data[v]
            if isinstance(val_obj, dict):
                has_clp = False
                price_idx = None
                for pk, pv in val_obj.items():
                    if isinstance(pv, int) and 0 <= pv < len(data):
                        val_str = str(data[pv])
                        if val_str == 'CLP':
                            has_clp = True
                        else:
                            try:
                                float(val_str)
                                price_idx = pv
                            except:
                                pass
                if has_clp and price_idx is not None:
                    try:
                        return int(float(data[price_idx]))
                    except:
                        pass
    return None

def scrape_spacio_detail(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.content, "html.parser")
        
        target_script = None
        for s in soup.find_all("script"):
            txt = s.get_text()
            if 'streamController.enqueue' in txt:
                target_script = txt
                break
        if not target_script:
            return []
            
        match = re.search(r'streamController\.enqueue\("(.*?)"\)', target_script, re.DOTALL)
        if not match:
            return []
            
        escaped_str = match.group(1)
        decoded_str = json.loads('"' + escaped_str + '"')
        data = json.loads(decoded_str)
        
        # Extract OpenGraph image
        img_tag = soup.find("meta", property="og:image")
        image_url = img_tag["content"] if img_tag else None
        
        variants = []
        seen_ids = set()
        for item in data:
            if isinstance(item, dict) and '_32' in item and '_36' in item:
                val_32_idx = item['_32']
                if isinstance(val_32_idx, int) and 0 <= val_32_idx < len(data):
                    val_32 = data[val_32_idx]
                    if isinstance(val_32, str) and val_32.startswith("gid://shopify/ProductVariant/"):
                        v_id = val_32.split("/")[-1]
                        if v_id in seen_ids:
                            continue
                        seen_ids.add(v_id)
                        
                        title_idx = item['_36']
                        title = data[title_idx] if (isinstance(title_idx, int) and 0 <= title_idx < len(data)) else "Unknown"
                        
                        product_name = None
                        product_obj_idx = item.get('_9')
                        if isinstance(product_obj_idx, int) and 0 <= product_obj_idx < len(data):
                            product_obj = data[product_obj_idx]
                            if isinstance(product_obj, dict) and '_36' in product_obj:
                                name_idx = product_obj['_36']
                                if isinstance(name_idx, int) and 0 <= name_idx < len(data):
                                    product_name = data[name_idx]
                                    
                        price = extract_spacio_price_dynamic(item, data)
                        
                        if title != "Unknown" and price is not None:
                            variants.append({
                                "provider": "Spacio Natural",
                                "product_name": product_name or "Desconocido",
                                "title": title,
                                "price": price,
                                "url": url,
                                "image_url": image_url
                            })
        return variants
    except Exception as e:
        print(f"Error scraping Spacio details from {url}: {e}")
        return []

# Spacio Natural collection scraper
def scrape_spacio():
    url = "https://www.spacionatural.cl/collections/insumos-para-hacer-velas"
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.content, "html.parser")
    
    product_links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("/products/"):
            full_url = "https://www.spacionatural.cl" + href.split("?")[0]
            product_links.add(full_url)
            
    print(f"Spacio Natural: Found {len(product_links)} products in collection. Scraping detailed variants...")
    
    results = []
    # Limit to max 25 products
    links_to_fetch = list(product_links)[:25]
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(scrape_spacio_detail, link): link for link in links_to_fetch}
        for future in as_completed(futures):
            res = future.result()
            if res:
                results.extend(res)
                
    return results

# Vimora Natural detail scraper
def scrape_vimora_detail(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.content, "html.parser")
        
        script_text = None
        for s in soup.find_all("script"):
            txt = s.get_text()
            if 'window.INIT.products.push' in txt:
                script_text = txt
                break
                
        if not script_text:
            return []
            
        match = re.search(r'window\.INIT\.products\.push\(([\s\S]*?)\);', script_text)
        if not match:
            return []
            
        data = json.loads(match.group(1).strip())
        p_data = data.get("product", {})
        product_name = p_data.get("title") or p_data.get("tg_display_name")
        
        # Extract OpenGraph image
        img_tag = soup.find("meta", property="og:image")
        image_url = img_tag["content"] if img_tag else None
        
        variants_list = data.get("variants", [])
        parsed_variants = []
        for v in variants_list:
            v_title = v.get("title")
            v_price = v.get("finalPrice")
            if v_title and v_price is not None:
                try:
                    price = int(float(str(v_price)))
                except:
                    price = None
                if price is not None:
                    parsed_variants.append({
                        "provider": "Vimora Natural",
                        "product_name": product_name or "Desconocido",
                        "title": v_title,
                        "price": price,
                        "url": url,
                        "image_url": image_url
                    })
        return parsed_variants
    except Exception as e:
        print(f"Error scraping Vimora details from {url}: {e}")
        return []

# Vimora Natural collection scraper
def scrape_vimora():
    url = "https://www.vimoranatural.cl/collection/insumos-velas-soja"
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.content, "html.parser")
    
    product_links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/product/" in href:
            full_url = href.split("?")[0]
            if not full_url.startswith("http"):
                full_url = "https://www.vimoranatural.cl" + full_url
            product_links.add(full_url)
            
    print(f"Vimora Natural: Found {len(product_links)} products in collection. Scraping detailed variants...")
    
    results = []
    # Limit to max 25 products
    links_to_fetch = list(product_links)[:25]
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(scrape_vimora_detail, link): link for link in links_to_fetch}
        for future in as_completed(futures):
            res = future.result()
            if res:
                results.extend(res)
                
    return results

# Fábrica de Velas Shopify products.json scraper
def scrape_fabricadevelas():
    print("Fábrica de Velas: Fetching variants from collection API...")
    products = []
    page = 1
    while True:
        url = f"https://fabricadevelas.cl/collections/insumos-velas/products.json?limit=250&page={page}"
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            break
        data = r.json()
        page_prods = data.get("products", [])
        if not page_prods:
            break
        for p in page_prods:
            name = p.get("title")
            variants = p.get("variants", [])
            img_url = p.get("images")[0].get("src") if p.get("images") else None
            for v in variants:
                v_title = v.get("title")
                price_str = str(v.get("price"))
                try:
                    price = int(float(price_str))
                except:
                    price = None
                if v_title and price is not None:
                    products.append({
                        "provider": "Fábrica de Velas",
                        "product_name": name,
                        "title": v_title,
                        "price": price,
                        "url": f"https://fabricadevelas.cl/products/{p.get('handle')}",
                        "image_url": img_url
                    })
        if len(page_prods) < 250:
            break
        page += 1
    print(f"Fábrica de Velas: Extracted {len(products)} variants.")
    return products

# MMPP WooCommerce crawler (Bypassing 403 blocks)
def scrape_mmpp_page(page_num):
    curl_headers = {
        "User-Agent": "curl/7.68.0",
        "Accept": "*/*"
    }
    url = f"https://mmpp.cl/categoria/insumos-para-velas/page/{page_num}/" if page_num > 1 else "https://mmpp.cl/categoria/insumos-para-velas/"
    try:
        r = requests.get(url, headers=curl_headers, timeout=TIMEOUT)
        if r.status_code != 200:
            return []
            
        soup = BeautifulSoup(r.content, "html.parser")
        products = soup.find_all(class_="product-small")
        
        results = []
        size_pattern = re.compile(r'(?:–|-)?\s*(\d+(?:\s*(?:ml|g|gr|kg|l|cc|kilo|litro)s?\b))', re.I)
        
        for p in products:
            a = p.find("a", href=True)
            if not a:
                continue
            href = a["href"]
            if "/categoria/" in href:
                continue
                
            title_el = p.find(class_=re.compile(r'woocommerce-loop-product__title|title|name', re.I))
            if not title_el:
                title_el = p.find(["h2", "h3"])
                
            title = title_el.get_text(strip=True) if title_el else ""
            if not title:
                continue
                
            price_el = p.find(class_=re.compile(r'price', re.I))
            if not price_el:
                continue
                
            price_txt = price_el.get_text(strip=True)
            price_digits = re.findall(r'\d[\d\.]*', price_txt)
            if not price_digits:
                continue
                
            last_price_str = price_digits[-1].replace(".", "")
            try:
                price = int(last_price_str)
            except:
                continue
                
            # Extract lazyload image from Fatsome WooCommerce layout
            img = p.find("img")
            image_url = img.get("data-src") or img.get("src") if img else None
            
            size_match = size_pattern.search(title)
            size = size_match.group(1) if size_match else "Default / Unspecified"
            
            cleaned_title = title
            if size_match:
                cleaned_title = title[:size_match.start()].strip(" –-")
                
            results.append({
                "provider": "MMPP",
                "product_name": cleaned_title,
                "title": size,
                "price": price,
                "url": href,
                "image_url": image_url
            })
        return results
    except Exception as e:
        print(f"Error scraping MMPP Page {page_num}: {e}")
        return []

def scrape_mmpp():
    print("MMPP: Crawling WooCommerce archive pages 1 to 9...")
    pages = list(range(1, 10))
    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(scrape_mmpp_page, p): p for p in pages}
        for future in as_completed(futures):
            res = future.result()
            results.extend(res)
    print(f"MMPP: Extracted {len(results)} variants.")
    return results

def agrupar_productos(all_extracted_items):
    grouped = {}
    for item in all_extracted_items:
        original_name = item["product_name"]
        norm_name = normalize_product_name(original_name)
        norm_size = normalize_size(item["title"])
        
        if not norm_name or not norm_size:
            continue
            
        category = classify_and_clean_product(norm_name, item["provider"])
        if category is None:
            continue
            
        if norm_name not in grouped:
            grouped[norm_name] = {
                "normalized_name": norm_name,
                "display_name": original_name,
                "category": category,
                "image_url": item.get("image_url"),
                "formats": {}
            }
        else:
            if len(original_name) < len(grouped[norm_name]["display_name"]) and len(original_name) > 3:
                grouped[norm_name]["display_name"] = original_name
            # Fallback image URL
            if not grouped[norm_name].get("image_url") and item.get("image_url"):
                grouped[norm_name]["image_url"] = item.get("image_url")
                
        if norm_size not in grouped[norm_name]["formats"]:
            grouped[norm_name]["formats"][norm_size] = []
            
        is_duplicate = False
        for existing in grouped[norm_name]["formats"][norm_size]:
            if existing["provider"] == item["provider"] and existing["original_size"] == item["title"] and existing["price"] == item["price"]:
                is_duplicate = True
                break
        if not is_duplicate:
            grouped[norm_name]["formats"][norm_size].append({
                "provider": item["provider"],
                "original_name": original_name,
                "original_size": item["title"],
                "price": item["price"],
                "original_price": f"${item['price']:,}".replace(",", "."),
                "url": item["url"]
            })
        
    # Convert grouped dict to sorted LIST of formats (fixes JS Object ordering bug)
    grouped_list = []
    for norm_name, data in grouped.items():
        sorted_formats_list = []
        format_order = ["15-20 g", "30 ml/g", "100 ml/g", "250 ml/g", "500 ml/g", "1 L / 1 Kg", "5 L / 5 Kg", "10 Kg", "20 Kg"]
        
        keys_to_sort = list(data["formats"].keys())
        keys_to_sort.sort(key=lambda k: format_order.index(k) if k in format_order else 999)
        
        for k in keys_to_sort:
            providers_list = data["formats"][k]
            providers_list.sort(key=lambda x: x["price"])
            sorted_formats_list.append({
                "size": k,
                "providers": providers_list
            })
            
        data["formats"] = sorted_formats_list
        grouped_list.append(data)
        
    grouped_list.sort(key=lambda x: x["display_name"])
    return grouped_list

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/extraer', methods=['POST'])
def extraer():
    results = []
    summary = {}
    
    # Run all scrapers in parallel
    scrapers = {
        "Samsa Aromas": scrape_samsa,
        "Spacio Natural": scrape_spacio,
        "Vimora Natural": scrape_vimora,
        "MMPP": scrape_mmpp,
        "Fábrica de Velas": scrape_fabricadevelas
    }
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(func): name for name, func in scrapers.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                prods = future.result()
                summary[name] = {"status": "success", "count": len(prods), "error": None}
                results.extend(prods)
            except Exception as e:
                summary[name] = {"status": "error", "count": 0, "error": str(e)}
                
    grouped_results = agrupar_productos(results)
    success_count = len([x for x in results if x.get("price") is not None])
    
    return jsonify({
        "success": True,
        "summary": summary,
        "grouped_products": grouped_results,
        "total_extracted": success_count
    })

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
