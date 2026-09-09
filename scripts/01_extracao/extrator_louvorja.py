from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
OUTPUT_FILE = ROOT_DIR / "Ideia" / "hinario_completo.json"

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import json
import os

# Configuração inicial
options = Options()
options.add_argument("--headless=new")
options.add_argument("--window-size=1920,1080") # FORÇA A TELA DE PC PARA NÃO QUEBRAR O LAYOUT
driver = webdriver.Chrome(options=options)
driver.get("https://app.louvorja.com.br")

# Usaremos um WebDriverWait centralizado para evitar repetição
wait = WebDriverWait(driver, 15)

try:
    print("Aguardando o carregamento da tela inicial...")
    
    css_hinario = "#app-container > div > main > div > div > div:nth-child(1) > div.v-expansion-panel-text.ma-0.pa-0 > div > div > div > div:nth-child(2)"
    botao_hinario = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, css_hinario)))
    botao_hinario.click()
    
    print("Hinário aberto. Iniciando a extração...")
    time.sleep(3)

    # Leitura do Estado Anterior (Resume Capability)
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            try:
                hinos_extraidos = json.load(f)
                if hinos_extraidos:
                    start_index = max(item["numero_indice"] for item in hinos_extraidos) + 1
                else:
                    start_index = 1
            except json.JSONDecodeError:
                hinos_extraidos = []
                start_index = 1
    else:
        hinos_extraidos = []
        start_index = 1

    total_hinos = 601 # Teste inicial com 5 hinos

    for i in range(start_index, total_hinos + 1):
        try:
            xpath_botao_abrir = f"//table/tbody/tr[{i}]/td[4]//button[4]"
            
            botao_abrir = wait.until(EC.presence_of_element_located((By.XPATH, xpath_botao_abrir)))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", botao_abrir)
            time.sleep(0.5) 
            
            driver.execute_script("arguments[0].click();", botao_abrir)
            
            # PAUSA CRUCIAL: Esperar a animação do modal terminar de abrir
            time.sleep(1.5)
            
            # TRUQUE DO [-1]: Usamos find_elements (plural) para pegar uma lista de todos os 
            # títulos/textos da tela e pegamos o último [-1], que sempre será o do modal ativo.
            titulos = driver.find_elements(By.CSS_SELECTOR, ".v-card-title")
            titulo_hino = titulos[-1].text

            textos = driver.find_elements(By.CSS_SELECTOR, ".v-card-text")
            texto_hino = textos[-1].text
            
            hinos_extraidos.append({
                "numero_indice": i,
                "titulo": titulo_hino,
                "letra": texto_hino
            })
            
            print(f"Hino {i} extraído: {titulo_hino}")
            
            # Salvamento Incremental: Reescreve o arquivo no disco a cada hino extraído
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(hinos_extraidos, f, ensure_ascii=False, indent=4)

            # TRUQUE DO ESCAPE: Em sites modernos (como Vuetify), a tecla ESC sempre fecha o modal superior.
            # Isso evita que o Selenium clique acidentalmente no botão errado.
            webdriver.ActionChains(driver).send_keys('\x1b').perform()
            
            time.sleep(0.5) # Pausa para o modal sumir suavemente
            
        except Exception as e:
            print(f"Erro na extração do índice {i}. Detalhe: {e}")
            # Se algo der muito errado, tenta forçar um ESC extra para limpar a tela
            webdriver.ActionChains(driver).send_keys('\x1b').perform()
            time.sleep(1)

    print("Processo concluído com sucesso! JSON gerado.")

finally:
    driver.quit()