import pandas as pd
import json
import re
import os
from pathlib import Path

# ==================== CONFIGURATION ====================
# Change these values as needed
INPUT_FILE = "RAW-DATA.csv"        # Your original exported CSV (old LH-DATA.csv)
OUTPUT_FILE = "clean.csv"     # The perfect import-ready file

# Target month/year for images (e.g. November 2025)
TARGET_YEAR_MONTH = "2025/11"   # Change to "2025/12" etc. if needed

# Brand to add (exactly as in your current site)
BRAND_NAME = "Leather Head"

# Attribute name (capital C!)
ATTRIBUTE_NAME = "Colors"

# =======================================================

def fix_image_urls(image_string):
    """Change /2025/06/ or any month → TARGET_YEAR_MONTH and .jpg/.png → .webp"""
    if not isinstance(image_string, str) or not image_string.strip():
        return image_string
    
    # Replace any 2025/XX with 2025/11 (or your target)
    image_string = re.sub(r'/2025/\d{2}/', f'/{TARGET_YEAR_MONTH}/', image_string)
    
    # Replace common image extensions with .webp
    image_string = re.sub(r'\.(jpe?g|png)(-scaled)?', '.webp', image_string, flags=re.IGNORECASE)
    
    # Fix any double // or -scaled still lingering
    image_string = image_string.replace('-scaled.webp', '.webp')
    
    return image_string.strip()

def fix_swatches_json(swatches_json):
    """Change "color" → "Colors" in the JSON key"""
    if not isinstance(swatches_json, str) or not swatches_json.strip():
        return swatches_json
    
    try:
        data = json.loads(swatches_json)
        if "color" in data:
            data[ATTRIBUTE_NAME] = data.pop("color")
        return json.dumps(data, ensure_ascii=False)
    except:
        # If JSON is broken, return original
        return swatches_json

def main():
    print(f"Reading {INPUT_FILE}...")
    df = pd.read_csv(INPUT_FILE, dtype=str, keep_default_na=False)
    
    print(f"Loaded {len(df)} rows.")
    
    # === 1. Add ID column at the beginning (leave blank for new import) ===
    if 'ID' not in df.columns:
        df.insert(0, 'ID', '')
    
    # === 2. Ensure all required columns exist (add missing ones as empty) ===
    required_columns = [
        "ID", "Type", "SKU", "GTIN, UPC, EAN, or ISBN", "Name", "Published", "Is featured?", 
        "Visibility in catalog", "Short description", "Description", "Date sale price starts", 
        "Date sale price ends", "Tax status", "Tax class", "In stock?", "Stock", "Low stock amount", 
        "Backorders allowed?", "Sold individually?", "Weight (kg)", "Length (mm)", "Width (mm)", 
        "Height (mm)", "Allow customer reviews?", "Purchase note", "Sale price", "Regular price", 
        "Categories", "Tags", "Shipping class", "Images", "Download limit", "Download expiry days", 
        "Parent", "Grouped products", "Upsells", "Cross-sells", "External URL", "Button text", 
        "Position", "Swatches Attributes", "Brands", "Blocksy Custom Data", "Blocksy Variation Images", 
        "Attribute 1 name", "Attribute 1 value(s)", "Attribute 1 visible", "Attribute 1 global", 
        "Attribute 1 default"
    ]
    
    for col in required_columns:
        if col not in df.columns:
            df[col] = ''
    
    # Reorder to match your site's exact export structure
    df = df[required_columns]
    
    # === 3. Fix image URLs ===
    if 'Images' in df.columns:
        df['Images'] = df['Images'].apply(fix_image_urls)
    
    # === 4. Fix variation images (some have single image in Images column) ===
    df['Images'] = df['Images'].apply(fix_image_urls)
    
    # === 5. Fix Swatches JSON: "color" → "Colors" ===
    if 'Swatches Attributes' in df.columns:
        df['Swatches Attributes'] = df['Swatches Attributes'].apply(fix_swatches_json)
    
    # === 6. Set Brand ===
    df['Brands'] = BRAND_NAME
    
    # === 7. Blocksy columns ===
    df['Blocksy Custom Data'] = '[]'
    df['Blocksy Variation Images'] = ''
    
    # === 8. Fix Attribute name ===
    df['Attribute 1 name'] = ATTRIBUTE_NAME
    
    # === 9. Fix Parent column (replace "id:1234" with parent product name) ===
    parent_map = {}
    for idx, row in df.iterrows():
        if row['Type'] == 'variable' and row['Name']:
            parent_map[row['Name']] = row['Name']
    
    def fix_parent(parent_val):
        if pd.isna(parent_val) or not parent_val:
            return ''
        if parent_val.startswith('id:'):
            # Try to find parent by old ID → use name from variable rows
            return ''  # We'll use name matching below
        return parent_val
    
    df['Parent'] = df['Parent'].apply(fix_parent)
    
    # For variations: set Parent = exact variable product name
    for idx, row in df.iterrows():
        if row['Type'] == 'variation' and row['Name']:
            # Extract parent name from variation name (e.g. "Product - Color" → "Product")
            possible_parent = row['Name'].rsplit(' - ', 1)[0]
            if possible_parent in parent_map:
                df.at[idx, 'Parent'] = possible_parent
    
    # === 10. Clean up Position (make sure variations have numbers) ===
    position_counter = {}
    for idx, row in df.iterrows():
        if row['Type'] == 'variation':
            parent = row['Parent']
import pandas as pd
import json
import re
import os
from pathlib import Path

# ==================== CONFIGURATION ====================
# Change these values as needed
INPUT_FILE = "RAW-DATA.csv"        # Your original exported CSV (old LH-DATA.csv)
OUTPUT_FILE = "clean.csv"     # The perfect import-ready file

# Target month/year for images (e.g. November 2025)
TARGET_YEAR_MONTH = "2025/11"   # Change to "2025/12" etc. if needed

# Brand to add (exactly as in your current site)
BRAND_NAME = "Leather Head"

# Attribute name (capital C!)
ATTRIBUTE_NAME = "Colors"

# =======================================================

def fix_image_urls(image_string):
    """Change /2025/06/ or any month → TARGET_YEAR_MONTH and .jpg/.png → .webp"""
    if not isinstance(image_string, str) or not image_string.strip():
        return image_string
    
    # Replace any 2025/XX with 2025/11 (or your target)
    image_string = re.sub(r'/2025/\d{2}/', f'/{TARGET_YEAR_MONTH}/', image_string)
    
    # Replace common image extensions with .webp
    image_string = re.sub(r'\.(jpe?g|png)(-scaled)?', '.webp', image_string, flags=re.IGNORECASE)
    
    # Fix any double // or -scaled still lingering
    image_string = image_string.replace('-scaled.webp', '.webp')
    
    return image_string.strip()

def fix_swatches_json(swatches_json):
    """Change "color" → "Colors" in the JSON key"""
    if not isinstance(swatches_json, str) or not swatches_json.strip():
        return swatches_json
    
    try:
        data = json.loads(swatches_json)
        if "color" in data:
            data[ATTRIBUTE_NAME] = data.pop("color")
        return json.dumps(data, ensure_ascii=False)
    except:
        # If JSON is broken, return original
        return swatches_json

def main():
    print(f"Reading {INPUT_FILE}...")
    df = pd.read_csv(INPUT_FILE, dtype=str, keep_default_na=False)
    
    print(f"Loaded {len(df)} rows.")
    
    # === 1. Add ID column at the beginning (leave blank for new import) ===
    if 'ID' not in df.columns:
        df.insert(0, 'ID', '')
    
    # === 2. Ensure all required columns exist (add missing ones as empty) ===
    required_columns = [
        "ID", "Type", "SKU", "GTIN, UPC, EAN, or ISBN", "Name", "Published", "Is featured?", 
        "Visibility in catalog", "Short description", "Description", "Date sale price starts", 
        "Date sale price ends", "Tax status", "Tax class", "In stock?", "Stock", "Low stock amount", 
        "Backorders allowed?", "Sold individually?", "Weight (kg)", "Length (mm)", "Width (mm)", 
        "Height (mm)", "Allow customer reviews?", "Purchase note", "Sale price", "Regular price", 
        "Categories", "Tags", "Shipping class", "Images", "Download limit", "Download expiry days", 
        "Parent", "Grouped products", "Upsells", "Cross-sells", "External URL", "Button text", 
        "Position", "Swatches Attributes", "Brands", "Blocksy Custom Data", "Blocksy Variation Images", 
        "Attribute 1 name", "Attribute 1 value(s)", "Attribute 1 visible", "Attribute 1 global", 
        "Attribute 1 default"
    ]
    
    for col in required_columns:
        if col not in df.columns:
            df[col] = ''
    
    # Reorder to match your site's exact export structure
    df = df[required_columns]
    
    # === 3. Fix image URLs ===
    if 'Images' in df.columns:
        df['Images'] = df['Images'].apply(fix_image_urls)
    
    # === 4. Fix variation images (some have single image in Images column) ===
    df['Images'] = df['Images'].apply(fix_image_urls)
    
    # === 5. Fix Swatches JSON: "color" → "Colors" ===
    if 'Swatches Attributes' in df.columns:
        df['Swatches Attributes'] = df['Swatches Attributes'].apply(fix_swatches_json)
    
    # === 6. Set Brand ===
    df['Brands'] = BRAND_NAME
    
    # === 7. Blocksy columns ===
    df['Blocksy Custom Data'] = '[]'
    df['Blocksy Variation Images'] = ''
    
    # === 8. Fix Attribute name ===
    df['Attribute 1 name'] = ATTRIBUTE_NAME
    
    # === 9. Fix Parent column (replace "id:1234" with parent product name) ===
    parent_map = {}
    for idx, row in df.iterrows():
        if row['Type'] == 'variable' and row['Name']:
            parent_map[row['Name']] = row['Name']
    
    def fix_parent(parent_val):
        if pd.isna(parent_val) or not parent_val:
            return ''
        if parent_val.startswith('id:'):
            # Try to find parent by old ID → use name from variable rows
            return ''  # We'll use name matching below
        return parent_val
    
    df['Parent'] = df['Parent'].apply(fix_parent)
    
    # For variations: set Parent = exact variable product name
    for idx, row in df.iterrows():
        if row['Type'] == 'variation' and row['Name']:
            # Extract parent name from variation name (e.g. "Product - Color" → "Product")
            possible_parent = row['Name'].rsplit(' - ', 1)[0]
            if possible_parent in parent_map:
                df.at[idx, 'Parent'] = possible_parent
    
    # === 10. Clean up Position (make sure variations have numbers) ===
    position_counter = {}
    for idx, row in df.iterrows():
        if row['Type'] == 'variation':
            parent = row['Parent']
            if parent not in position_counter:
                position_counter[parent] = 0
            position_counter[parent] += 1
            df.at[idx, 'Position'] = position_counter[parent]
    
    # === 11. Final cleanup ===
    df.fillna('', inplace=True)
    
    # === Save ===
    df.to_csv(OUTPUT_FILE, index=False, encoding='utf-8')
    print(f"\nSUCCESS! Clean file saved as: {OUTPUT_FILE}")
    print(f"   -> All images updated to {TARGET_YEAR_MONTH}/*.webp")
    print(f"   -> Swatches fixed to use '{ATTRIBUTE_NAME}'")
    print(f"   -> Brand set to '{BRAND_NAME}'")
    print(f"   -> Parent links fixed by product name")
    print(f"   -> Ready for WooCommerce import!")

if __name__ == "__main__":
    if not os.path.exists(INPUT_FILE):
        print(f"ERROR: {INPUT_FILE} not found! Place your old CSV in the same folder.")
    else:
        main()