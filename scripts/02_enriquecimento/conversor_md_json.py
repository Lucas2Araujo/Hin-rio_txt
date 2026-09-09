from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent

import json
import re

def parse_hinario(filepath):
    # Lê o arquivo Markdown
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Separa os hinos baseando-se no cabeçalho "## Hino"
    hymns_raw = re.split(r'\n## Hino ', content)
    
    hymns_data = []
    
    for hymn_raw in hymns_raw:
        if not hymn_raw.strip() or hymn_raw.startswith('# Base'):
            continue
            
        lines = hymn_raw.strip().split('\n')
        
        # A primeira linha contém o número e o título (ex: "1: Santo, Santo, Santo!")
        title_match = re.match(r'(\d+):\s*(.*)', lines[0])
        if not title_match:
            continue
            
        hymn_number = int(title_match.group(1))
        
        # Inicializa o dicionário APENAS com os campos solicitados
        hymn_dict = {
            "numero": hymn_number,
            "texto_base_motivador": "", 
            "textos_relacionados": [], # Ficará sempre vazio
            "categoria": "",
            "subcategoria": ""
        }
        
        # Processa as linhas de metadados
        for line in lines[1:]:
            # Ao encontrar o cabeçalho da letra, interrompe o loop
            if line.startswith('### Letra do Hino:'):
                break 
            
            if '**Categoria:**' in line:
                match = re.search(r'\*\*Categoria:\*\*\s*(.*?)\s*\|\s*\*\*Subcategoria:\*\*\s*(.*)', line)
                if match:
                    hymn_dict["categoria"] = match.group(1).strip()
                    hymn_dict["subcategoria"] = match.group(2).strip()
                    
            # Captura o texto base que não estava sendo capturado no script original
            elif '**Texto Base (Motivador):**' in line:
                hymn_dict["texto_base_motivador"] = line.replace('**Texto Base (Motivador):**', '').strip()

            # Tudo o que não for categoria, subcategoria ou texto base
            # (vídeos, textos relacionados, temas e autores) é ignorado no loop.

        hymns_data.append(hymn_dict)
        
    return hymns_data

# Configurações de entrada e saída
input_file = ROOT_DIR / 'Textos' / 'Hinario_NotebookLM.md'
output_file = ROOT_DIR / 'basesdedados' / 'hinario_indexado.json'

try:
    print("Iniciando a conversão...")
    dados_processados = parse_hinario(input_file)
    
    # Salva os dados em formato JSON
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(dados_processados, f, ensure_ascii=False, indent=4)
        
    print(f"Sucesso! {len(dados_processados)} hinos foram exportados para o arquivo '{output_file}'.")
    print("Foram mantidos APENAS: número, texto base, categoria, subcategoria e a linha de textos relacionados (vazia).")
    
except FileNotFoundError:
    print(f"Erro: O arquivo '{input_file}' não foi encontrado na pasta atual.")
except Exception as e:
    print(f"Ocorreu um erro inesperado: {e}")