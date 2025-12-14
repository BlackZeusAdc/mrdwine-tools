import streamlit as st
import pandas as pd
import io
import re
import unicodedata
import sqlite3
import os

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Mr D Wine - SEO Master Tool", page_icon="🍷", layout="wide")

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    h1 { color: #800020; }
    .stButton>button { width: 100%; font-weight: bold; border-radius: 8px; }
    .metric-card { background-color: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); text-align: center; }
    .metric-value { font-size: 24px; font-weight: bold; color: #800020; }
    .metric-label { font-size: 14px; color: #666; }
    .success-box { background-color: #d1e7dd; color: #0f5132; padding: 10px; border-radius: 5px; margin: 10px 0; }
    .warning-box { background-color: #fff3cd; color: #664d03; padding: 10px; border-radius: 5px; margin: 10px 0; }
    </style>
    """, unsafe_allow_html=True)

# --- SISTEMA DE GESTIÓN DE USUARIOS ---
USUARIOS_AUTORIZADOS = {
    "jose": "admin123",
    "carlos": "arquitecto",
    "webmaster": "secure2025"
}

def check_login():
    if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
    if not st.session_state['logged_in']:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown("### 🔒 Acceso Restringido - Billionz Digital")
            u = st.text_input("Usuario")
            p = st.text_input("Contraseña", type="password")
            if st.button("Entrar"):
                if u in USUARIOS_AUTORIZADOS and USUARIOS_AUTORIZADOS[u] == p:
                    st.session_state['logged_in'] = True
                    st.rerun()
                else: st.error("Acceso denegado")
        return False
    return True

# --- BASE DE DATOS (SQLite) ---
DB_FILE = 'mrdwine_inventory.db'

def limpiar_texto_handle(texto):
    if pd.isna(texto): return ""
    texto = str(texto).lower().strip()
    texto = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('utf-8')
    texto = re.sub(r'[^a-z0-9]+', '-', texto)
    return texto.strip('-')

def generar_search_key(handle, vintage, size):
    """
    Crea la Llave Maestra de Búsqueda (KEY v2).
    Key = Handle + Option1 Value (Vintage) + Option2 Value (Size)
    """
    h = limpiar_texto_handle(str(handle))
    v = limpiar_texto_handle(str(vintage))
    s = limpiar_texto_handle(str(size)) 
    return f"{h}|{v}|{s}"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS products (
            variant_id TEXT,
            handle TEXT,
            sku TEXT,
            title TEXT,
            vendor TEXT,
            option1_value TEXT, -- Vintage
            option2_value TEXT, -- Size (Format)
            search_key TEXT PRIMARY KEY
        )
    ''')
    conn.commit()
    conn.close()

def sincronizar_bd(df):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    col_map = {
        'Handle': 'handle', 'Variant ID': 'variant_id', 'ID': 'variant_id', 
        'Variant SKU': 'sku', 'SKU': 'sku', 'Title': 'title', 'Vendor': 'vendor',
        'Option1 Value': 'option1', 'Option2 Value': 'option2'
    }
    df = df.rename(columns=col_map)
    
    count = 0
    errores = 0
    
    for _, row in df.iterrows():
        v_id = str(row.get('variant_id', '')).replace('.0', '')
        
        if not v_id or v_id == 'nan' or v_id == '':
            continue

        handle = str(row.get('handle', ''))
        sku = str(row.get('sku', ''))
        title = str(row.get('title', ''))
        vendor = str(row.get('vendor', ''))
        opt1 = str(row.get('option1', ''))
        opt2 = str(row.get('option2', '')) 
        
        search_key = generar_search_key(handle, opt1, opt2)
        
        try:
            cursor.execute('''
                INSERT INTO products (variant_id, handle, sku, title, vendor, option1_value, option2_value, search_key) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(search_key) DO UPDATE SET
                variant_id=excluded.variant_id,
                handle=excluded.handle,
                sku=excluded.sku,
                title=excluded.title,
                vendor=excluded.vendor,
                option1_value=excluded.option1_value,
                option2_value=excluded.option2_value
            ''', (v_id, handle, sku, title, vendor, opt1, opt2, search_key))
            count += 1
        except Exception:
            errores += 1
        
    conn.commit()
    conn.close()
    
    msg = "✅ Sincronización completada."
    if errores > 0: msg += f" (Omitidos {errores} duplicados)"
    return count, errores, msg

# --- TRADUCTOR DE CABECERAS (HEADER VENDOR) ---
def normalizar_headers_vendor(df):
    column_mapping = {}
    synonyms = {
        'Vendor': ['marca', 'producer', 'brand', 'bodega', 'proveedor'],
        'Title': ['nombre_vino', 'nombre vino', 'product name', 'wine_name', 'nombre', 'producto'],
        'Option1 Value': ['añada', 'vintage', 'año', 'anio', 'year'],
        'Option2 Value': ['presentacion', 'size', 'formato', 'tamaño', 'volumen', 'capacity', 'ml'],
        'Variant Price': ['precio', 'price', 'precio venta', 'costo', 'pvp'],
        'Variant Inventory Qty': ['inventario', 'stock', 'cantidad', 'qty', 'existencia'],
        'Variant SKU': ['sku', 'referencia', 'codigo'],
        'Varietal': ['varietal', 'uva', 'tipo de uva', 'grape'],
        'Region': ['region', 'zona', 'denominacion', 'appellation']
    }
    
    for col in df.columns:
        col_lower = str(col).lower().strip()
        for standard, alias_list in synonyms.items():
            if col_lower == standard.lower():
                column_mapping[col] = standard; break
            if col_lower in alias_list:
                column_mapping[col] = standard; break
                
    if column_mapping: df = df.rename(columns=column_mapping)
    return df

# --- MOTOR SEO ---
PAIRING_DICT = {
    'cabernet': 'grilled meats', 'sauvignon': 'grilled meats', 'merlot': 'roasted poultry', 
    'pinot noir': 'salmon & duck', 'syrah': 'bbq ribs', 'shiraz': 'bbq ribs', 
    'zinfandel': 'pasta & burgers', 'malbec': 'red meats', 'chardonnay': 'creamy pasta', 
    'sauvignon blanc': 'fresh seafood', 'riesling': 'spicy cuisine', 'champagne': 'oysters & caviar', 
    'sparkling': 'appetizers', 'rose': 'summer salads', 'tempranillo': 'lamb chops', 
    'sangiovese': 'tomato pasta', 'nebbiolo': 'truffles & risotto'
}
REGION_MAP = {
    'russian river valley': 'Russian River', 'napa valley': 'Napa', 'columbia valley': 'Columbia Valley', 
    'willamette valley': 'Willamette', 'sonoma coast': 'Sonoma Coast', 'alexander valley': 'Alexander Valley', 
    'paso robles': 'Paso Robles', 'ribera del duero': 'Ribera del Duero', 'rioja doca': 'Rioja', 
    'chianti classico': 'Chianti', 'brunello di montalcino': 'Brunello'
}

SIZE_TO_GRAMS = {
    '375ml': 680, 
    '500ml': 907, 
    '750ml': 1360,
    '1.5L': 2720, '1.5l': 2720, 
    '3L': 5440, '3l': 5440,
    'Half Bottle': 680, 
    'Bottle': 1360, 
    'Magnum': 2720, 
    'Double Magnum': 5440
}

def extraer_score_del_html(html_text):
    if pd.isna(html_text): return None
    match = re.search(r'(\d{2,3})\s*(?:Pts|pts|Points)', str(html_text))
    if match: return int(match.group(1))
    return None

def detectar_varietal(texto):
    texto = str(texto).lower()
    for uva in PAIRING_DICT:
        if uva in texto: return uva
    return "fine wine"

def normalizar_region(texto):
    if pd.isna(texto): return ""
    texto_lower = str(texto).lower()
    for key, val in REGION_MAP.items():
        if key in texto_lower: return val
    return str(texto).title()

def generar_seo_title(anio, nombrebase, region, score, es_unico=False):
    """
    Genera el Title Tag optimizado.
    Regla: El Año SOLO se muestra si el producto TIENE variantes.
    """
    nombre_limpio = nombrebase.strip()
    
    # --- LÓGICA CORREGIDA Y SIMPLIFICADA ---
    if es_unico:
        anio_str = str(anio) if anio and str(anio).upper() != "NV" else ""
    else:
        anio_str = ""  # NO mostrar año en productos con variantes
    
    
    # Construcción Base
    if anio_str:
        base_title = f"{anio_str} {nombre_limpio}".strip()
    else:
        base_title = nombre_limpio.strip()
    
    # Componentes Opcionales
    components = []
    if region:
        components.append(str(region))
    components.append("Best price")
    
    # Límite de 60 caracteres
    final_title = base_title
    for comp in components:
        test_title = f"{final_title} {comp}"
        if len(test_title) <= 60:
            final_title = test_title
        else:
            continue
            
    if len(final_title) > 60:
        final_title = final_title[:60]
        last_space = final_title.rfind(' ')
        if last_space != -1:
            final_title = final_title[:last_space]
    
    # Formato Minúscula (Sentence case)
    return final_title.capitalize()



def generar_meta_description(row, titulo_limpio, region, varietal, score):
    """
    Genera Meta Description (Máx ~155 chars estándar SEO).
    Estrategia: Construcción por oraciones completas para evitar cortes bruscos.
    Formato: Sentence case (Solo primera letra mayúscula).
    """
    # 1. Limpieza preventiva de datos (evita que salgan listas de tags sucias)
    titulo = str(titulo_limpio).strip()
    
    # Limpiamos region y varietal para que no sean listas largas separadas por comas
    # Si viene "Mendoza, Argentina, Valle de Uco", nos quedamos solo con lo primero antes de la coma para que sea corto y natural.
    region_corta = str(region).split(',')[0].strip() if region else "best regions"
    varietal_corto = str(varietal).split(',')[0].strip() if varietal else "fine wine"
    
    try: precio = float(row.get('Variant Price', 0))
    except: precio = 0
    
    score_txt = f"Rated {score} pts." if score else ""

    # 2. Definimos bloques de texto por prioridad (Pesos)
    # Bloque A: La acción principal (Vital)
    block_a = f"Shop {titulo}."
    
    # Bloque B: Contexto (Región y Tipo) - Le da naturalidad
    # Ej: "A prestigious Malbec from Mendoza."
    block_b = f"A prestigious {varietal_corto} from {region_corta}."
    
    # Bloque C: Gancho de venta (Cierre)
    if precio > 0 and precio < 50:
        block_c = "Best price & fast shipping at Mr D Wine."
    else:
        block_c = f"{score_txt} Secure your bottle at Mr D Wine."

    # 3. Ensamblaje inteligente (Evita cortes bruscos)
    # Límite SEO estándar: 155 caracteres (60 es muy poco para description, es para titles)
    LIMIT = 155 
    
    description = block_a
    
    # Intentamos agregar Bloque B (Descripción)
    if len(description) + len(block_b) + 1 <= LIMIT:
        description += " " + block_b
        
    # Intentamos agregar Bloque C (Cierre)
    # Limpiamos block_c de espacios extra o puntuación flotante antes de medir
    block_c = block_c.strip().strip(',').strip()
    
    if len(description) + len(block_c) + 1 <= LIMIT:
        description += " " + block_c

    # 4. Formato final
    # Aseguramos que termine en punto si no lo tiene
    if not description.endswith('.'):
        description += "."
        
    # Aplicamos Sentence case (Solo primera letra mayúscula)
    return description.capitalize()

# --- MOTOR DE LIMPIEZA ---
def extraer_anio(texto):
    if pd.isna(texto): return None
    texto = str(texto).upper()
    if re.search(r'\bNV\b', texto): return "NV"
    match = re.search(r'\b(19[5-9]\d|20[0-2]\d)\b', texto)
    if match: return match.group(0)
    return "NV" 

def normalizar_nombre_base(titulo):
    if pd.isna(titulo): return ""
    texto = str(titulo).lower()
    texto = re.sub(r'\b(19|20)\d{2}\b', '', texto)
    texto = re.sub(r'\bnv\b', '', texto)
    texto = re.sub(r'\b\d+(\.\d+)?\s?(ml|l|cl)\b', '', texto)
    texto = re.sub(r'\bcase\b', '', texto)
    texto = re.sub(r'\b\dx\d+\b', '', texto)
    texto = re.sub(r'signature\s*\(sgws\)', '', texto)
    texto = re.sub(r'sgws', '', texto)
    stopwords = ['docg', 'doc', 'do', 'igt', 'estate', 'reserve', 'reserva', 'gran', 'grand', 'cru', 'classico', 'bottle', 'copy']
    for word in stopwords: texto = re.sub(r'\b' + word + r'\b', '', texto)
    texto = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('utf-8')
    texto = re.sub(r'[^a-z0-9\s]', '', texto) 
    texto = re.sub(r'\s+', ' ', texto).strip() 
    return texto

def limpiar_texto_handle(texto):
    if pd.isna(texto): return ""
    texto = str(texto).lower().strip()
    texto = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('utf-8')
    texto = re.sub(r'[^a-z0-9]+', '-', texto)
    return texto.strip('-')

# --- LÓGICA DE PROCESAMIENTO ---
COLUMNAS_SALIDA_EXACTAS = [
    "Handle", "Title", "Body (HTML)", "Vendor", "Product Category", "Type", "Tags", "Published",
    "Variant ID", "Variant Price", "Variant Inventory Qty", "Variant SKU", 
    "Image Src", "Image Alt Text", "Variant Image", 
    "SEO Title", "SEO Description", "Status",
    "Option1 Name", "Option1 Value", "Option2 Name", "Option2 Value", 
    "Variant Compare At Price", "Variant Barcode", "Variant Weight", 
    "Variant Weight Unit", "Variant Grams", "Variant Inventory Tracker", "Cost per item",
    "Score", "Varietal" 
]

def generar_sabana_actualizacion(df):
    log = []
    df = normalizar_headers_vendor(df)
    
    requeridas = ['Title', 'Option1 Value', 'Variant Price', 'Variant Inventory Qty']
    faltantes = [c for c in requeridas if c not in df.columns]
    if faltantes: return None, f"❌ Error: Faltan columnas: {', '.join(faltantes)}", []
    
    cols_deseadas = [
        'Variant ID', 'Handle', 'Variant SKU', 'Variant Price', 
        'Variant Inventory Qty', 'Option1 Value', 'Option2 Value'
    ]
    for c in cols_deseadas:
        if c not in df.columns: df[c] = ""
            
    df_clean = df[cols_deseadas].copy()
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    for idx, row in df.iterrows():
        title = row.get('Title', '')
        handle_inferido = limpiar_texto_handle(title)
        
        vintage = row.get('Option1 Value', '')
        
        # --- CORRECCIÓN CRÍTICA: Mapeo de Option2 usando nombres exactos ---
        size_value = str(row.get('Size (product.metafields.pundit.format_size)', ''))
        if not size_value or size_value.lower() == 'nan':
             size_value = str(row.get('Presentation (product.metafields.pundit.format)', ''))
        
        # Fallback a la columna normal si no se encuentra en metafields
        if not size_value or size_value.lower() == 'nan':
             size_value = str(row.get('Option2 Value', '')) 
        
        if not size_value or size_value.lower() == 'nan':
            size_value = '750ml' # Default para búsqueda

        size = size_value
        
        search_key = generar_search_key(handle_inferido, vintage, size)
        
        cursor.execute("SELECT variant_id, handle FROM products WHERE search_key = ?", (search_key,))
        res = cursor.fetchone()
        
        if not res:
            cursor.execute("SELECT variant_id, handle FROM products WHERE search_key LIKE ?", (f"{handle_inferido}|{limpiar_texto_handle(vintage)}%",))
            res = cursor.fetchone()

        if res:
            df_clean.at[idx, 'Variant ID'] = res[0]
            df_clean.at[idx, 'Handle'] = res[1]
        else:
            log.append(f"⚠️ No encontrado en BD: {title} ({vintage}). Se omitirá.")
    
    conn.close()
    
    sin_match = df_clean[ (df_clean['Variant ID'] == "") | (df_clean['Handle'] == "") ]
    if not sin_match.empty:
        log.append(f"🚨 {len(sin_match)} productos no encontrados en BD.")
    
    df_clean = df_clean[ (df_clean['Variant ID'] != "") & (df_clean['Handle'] != "") ]
    
    return df_clean, "✅ Actualización Generada", log

def procesar_agrupacion_inteligente(df):
    log = []
    lista_redirecciones = []
    
    # 1. Normalización básica
    df = normalizar_headers_vendor(df)
    
    # Corrección para el archivo de Signature si usa 'Description' en vez de 'Title'
    if 'Title' not in df.columns:
        if 'Description' in df.columns:
            df = df.rename(columns={'Description': 'Title'})
        else:
            return None, "❌ Error: Falta columna 'Title' (o 'Description').", [], 0
    
    # Pre-cálculos
    df['__anio_detectado'] = df['Title'].apply(extraer_anio)
    df['__nombre_base'] = df['Title'].apply(normalizar_nombre_base)
    
    if 'Vendor' in df.columns:
        df['__vendor_norm'] = df['Vendor'].astype(str).str.lower().str.strip()
        df['__vendor_norm'] = df['__vendor_norm'].apply(lambda x: re.sub(r'\.', '', x))
    else:
        df['__vendor_norm'] = 'generico'
    
    df['__group_key'] = df['__vendor_norm'] + "_" + df['__nombre_base']
    df['__handle_canonico'] = df.apply(lambda x: limpiar_texto_handle(f"{x['__nombre_base']}"), axis=1)
    
    rows_finales = []
    
    grupos = df.groupby('__group_key')
    clusters_encontrados = 0
    total_variantes = 0
    
    for name, group in grupos:
        group = group.sort_values(by='__anio_detectado', ascending=False)
        es_producto_unico = (len(group) == 1)
        
        if not es_producto_unico:
            clusters_encontrados += 1
            total_variantes += (len(group) - 1)
        
        padre = group.iloc[0]
        handle = padre['__handle_canonico']
        titulo_padre = padre['__nombre_base'].title()
        html_body = str(padre.get('Body (HTML)', ''))
        score = extraer_score_del_html(html_body)
        varietal = detectar_varietal(titulo_padre + html_body)
        
        region = "Region"
        if 'Tags' in padre and pd.notna(padre['Tags']):
            region = normalizar_region(str(padre['Tags']))
        if region == "Region" and 'Appellation' in padre:
             region = normalizar_region(str(padre['Appellation']))
        
        es_primera_variante = True
        
        for idx, row in group.iterrows():
            fila = {col: '' for col in COLUMNAS_SALIDA_EXACTAS}
            fila['Handle'] = handle
            
            # --- PADRE (Datos Principales SEO y Títulos) ---
            if es_primera_variante:
                fila['Title'] = titulo_padre
                fila['Body (HTML)'] = row.get('Body (HTML)', '')
                fila['Vendor'] = row.get('Vendor', '')
                fila['Product Category'] = row.get('Product Category', 'Food, Beverages & Tobacco > Beverages > Alcoholic Beverages > Wine')
                fila['Type'] = row.get('Type', 'Wine')
                fila['Tags'] = row.get('Tags', '')
                fila['Published'] = 'TRUE'
                fila['Status'] = 'active'
                fila['Score'] = score if score else ''
                fila['Varietal'] = varietal
                
                anio_seo = row['__anio_detectado']
                seo_title = generar_seo_title(anio_seo, titulo_padre, region, score, es_unico=es_producto_unico)
                fila['SEO Title'] = seo_title
                fila['SEO Description'] = generar_meta_description(row, titulo_padre, region, varietal, score)
                
                es_primera_variante = False
            
            # --- VARIANTE (Datos Técnicos) ---
            if 'Variant ID' in row: fila['Variant ID'] = row['Variant ID']
            
            # Option 1: Vintage
            anio = row['__anio_detectado']
            fila['Option1 Name'] = 'Vintage'
            fila['Option1 Value'] = anio
            
            # --- LÓGICA DE OPCIÓN 2 (MAPEO EXACTO) ---
            
            # 1. Option2 Name <- Presentation (product.metafields.pundit.format)
            # Buscamos la columna exacta que indicaste
            opt2_name = str(row.get('Presentation (product.metafields.pundit.format)', ''))
            
            # Fallback: Si esa columna viene vacía, intentamos buscar 'Format' o usamos un default 'Presentation'
            if not opt2_name or opt2_name.lower() == 'nan':
                 opt2_name = str(row.get('Format', '')) 
            if not opt2_name or opt2_name.lower() == 'nan':
                 opt2_name = 'Presentation' # Default seguro

            # 2. Option2 Value <- Size (product.metafields.pundit.format_size)
            # Buscamos la columna exacta que indicaste
            opt2_value = str(row.get('Size (product.metafields.pundit.format_size)', ''))
            
            # Fallback: Si esa columna está vacía (ej. archivos de otros proveedores como Signature), buscamos los alternativos
            if not opt2_value or opt2_value.lower() == 'nan': opt2_value = str(row.get('Option2 Value', ''))
            if not opt2_value or opt2_value.lower() == 'nan': opt2_value = str(row.get('Sz', ''))
            if not opt2_value or opt2_value.lower() == 'nan': opt2_value = str(row.get('sz', ''))
            if not opt2_value or opt2_value.lower() == 'nan': opt2_value = str(row.get('Pack/Sz', ''))
            if not opt2_value or opt2_value.lower() == 'nan': opt2_value = '750ml' # Último recurso

            # Asignación Final
            fila['Option2 Name'] = opt2_name
            fila['Option2 Value'] = opt2_value
            
            # Calculamos peso basado en el valor del tamaño
            grams = SIZE_TO_GRAMS.get(opt2_value, 1360)
            fila['Variant Grams'] = grams
            fila['Variant Weight'] = round(grams / 453.592, 2)
            fila['Variant Weight Unit'] = 'lb'
            
            # Resto de columnas
            sku_val = str(row.get('Variant SKU', ''))
            if not sku_val or sku_val == 'nan': sku_val = str(row.get('Item #', ''))
            
            price_val = str(row.get('Variant Price', ''))
            if not price_val or price_val == 'nan': price_val = str(row.get('Reg Price', ''))

            fila['Variant SKU'] = sku_val
            fila['Variant Price'] = price_val
            fila['Variant Inventory Qty'] = row.get('Variant Inventory Qty', '')
            fila['Image Src'] = row.get('Image Src', '')
            fila['Image Alt Text'] = row.get('Image Alt Text', '')
            fila['Variant Image'] = row.get('Variant Image', '')
            fila['Cost per item'] = row.get('Cost per item', '')
            fila['Variant Compare At Price'] = row.get('Variant Compare At Price', '')
            
            barcode_val = str(row.get('Variant Barcode', ''))
            if not barcode_val or barcode_val.lower() == 'nan': barcode_val = str(row.get('UPC', ''))
            if not barcode_val or barcode_val.lower() == 'nan': barcode_val = str(row.get('upc', ''))
            fila['Variant Barcode'] = barcode_val
            
            fila['Variant Inventory Tracker'] = 'shopify'
            rows_finales.append(fila)
    
    df_final = pd.DataFrame(rows_finales)
    df_final = df_final[COLUMNAS_SALIDA_EXACTAS]
    
    metrics = {
        'total_rows': len(df_final),
        'clusters': clusters_encontrados,
        'variantes': total_variantes,
        'redirecciones': len(lista_redirecciones)
    }
    
    return df_final, log, pd.DataFrame(lista_redirecciones), metrics
# --- APP ---

def main_app():
    init_db()
    with st.sidebar:
        st.write("👤 Admin Conectado")
        st.subheader("🗄️ BD Maestra")
        db_file = st.file_uploader("Sincronizar BD", type=['csv', 'xlsx'], key="db")
        if db_file and st.button("Sincronizar"):
            try:
                df = pd.read_csv(db_file) if db_file.name.endswith('.csv') else pd.read_excel(db_file)
                tot, _, msg = sincronizar_bd(df)
                st.success(f"{msg} ({tot} productos)")
            except Exception as e: st.error(str(e))
        if st.button("Salir"): st.session_state['logged_in'] = False; st.rerun()

    st.title("🍷 Mr D Wine: SEO & Inventory Engine v8.7")
    
    tab1, tab2 = st.tabs(["🔄 ACTUALIZAR (Vendor)", "✨ CREAR (Nuevos)"])

    with tab1:
        st.header("Actualización Inteligente (Vendor Match)")
        st.info("Sube archivo del proveedor. Se cruza con BD usando: Nombre + Año + Tamaño.")
        f = st.file_uploader("Archivo Proveedor", type=['csv', 'xlsx'], key="upd")
        if f and st.button("Procesar Actualización"):
            try:
                df = pd.read_csv(f) if f.name.endswith('.csv') else pd.read_excel(f)
                res, msg, logs = generar_sabana_actualizacion(df)
                if res is not None:
                    st.success(msg)
                    if logs: 
                        with st.expander("⚠️ Alertas de Cruce", expanded=True): 
                            for l in logs: st.write(l)
                    st.download_button("⬇️ Descargar Actualización", res.to_csv(index=False).encode('utf-8'), "MrDWine_Update_Clean.csv", "text/csv")
                else: st.error(msg)
            except Exception as e: st.error(str(e))

    with tab2:
        st.header("Creación + SEO Automático")
        
        if 'creacion_data' not in st.session_state:
            st.session_state['creacion_data'] = None
            
        f_cre = st.file_uploader("Archivo Nuevos Productos", type=['csv', 'xlsx'], key="cre")
        
        col_btn1, col_btn2 = st.columns([1, 4])
        with col_btn1:
            if f_cre and st.button("Generar Importación"):
                try:
                    if f_cre.name.endswith('.csv'):
                        try: df = pd.read_csv(f_cre, encoding='utf-8')
                        except: df = pd.read_csv(f_cre, encoding='latin-1')
                    else: df = pd.read_excel(f_cre)
                    
                    res, logs, redirs, metrics = procesar_agrupacion_inteligente(df)
                    st.session_state['creacion_data'] = {
                        'res': res, 'logs': logs, 'redirs': redirs, 'metrics': metrics
                    }
                except Exception as e: st.error(str(e))
        
        with col_btn2:
            if st.button("🗑️ Reiniciar", type="primary"):
                st.session_state['creacion_data'] = None
                st.rerun()

        data = st.session_state['creacion_data']
        if data:
            st.markdown("---")
            m = data['metrics']
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Productos", m['total_rows'])
            c2.metric("Grupos", m['clusters'])
            c3.metric("Variantes", m['variantes'])
            c4.metric("Redirecciones", m['redirecciones'])
            
            st.success("✅ Procesamiento Exitoso.")

            if data['logs']:
                with st.expander("⚠️ Ver Alertas SEO", expanded=True):
                    for l in data['logs']: st.write(l)

            with st.expander("🔍 Vista Previa", expanded=True):
                st.dataframe(data['res'][['Title', 'SEO Title', 'SEO Description', 'Score', 'Varietal']].head(10), use_container_width=True)
            
            c_d1, c_d2 = st.columns(2)
            with c_d1: st.download_button("🚀 Descargar Productos", data['res'].to_csv(index=False).encode('utf-8'), "MrDWine_IMPORT_READY.csv", "text/csv")
            with c_d2: 
                if not data['redirs'].empty: st.download_button("🔗 Redirecciones 301", data['redirs'].to_csv(index=False).encode('utf-8'), "MrDWine_REDIRECTS.csv", "text/csv")
                else: st.info("Sin redirecciones.")

if __name__ == "__main__":
    if check_login(): main_app()
