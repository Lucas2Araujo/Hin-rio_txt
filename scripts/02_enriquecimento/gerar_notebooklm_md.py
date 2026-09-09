from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
INPUT_CSV = ROOT_DIR / "basesdedados" / "BD_Hinario_Master.csv"
OUTPUT_MD = ROOT_DIR / "Textos" / "Hinario_NotebookLM.md"

import pandas as pd
import math

print("Iniciando a geração do arquivo Markdown para o NotebookLM...")

# 1. Carrega o CSV Master que contém TODAS as informações unidas
df = pd.read_csv(INPUT_CSV)

# 2. Cria ou sobrescreve o arquivo Markdown
with open(OUTPUT_MD, 'w', encoding='utf-8') as f:
    f.write("# Base de Conhecimento - Hinário\n\n")
    f.write("Este documento contém as letras, autores, categorias e referências bíblicas de todos os hinos.\n\n")
    f.write("---\n\n")
    
    # 3. Itera linha por linha para montar o documento
    for index, row in df.iterrows():
        f.write(f"## Hino {row['Número']}: {row['Título']}\n\n")
        
        # AJUSTE AQUI: Puxando exatamente os nomes das colunas que geramos no Script 1
        temas = row.get('Temas Relacionados', 'N/A')
        textos_relacionados = row.get('Textos Relacionados', 'N/A') 
        texto_base = row.get('Texto Base', 'N/A') 
        categoria = row.get('Categoria', 'N/A')
        subcategoria = row.get('Subcategoria', 'N/A')
        autor_letra = row.get('Autor da Letra', 'N/A')
        autor_musica = row.get('Autor da Música', 'N/A')
        link_video = row.get('Link do Vídeo', 'N/A')
        
        # Garantia contra valores nulos (NaN) do Pandas
        if pd.isna(textos_relacionados): textos_relacionados = 'N/A'
        if pd.isna(texto_base): texto_base = 'N/A'
        if pd.isna(temas): temas = 'N/A'
        if pd.isna(autor_letra): autor_letra = 'N/A'
        if pd.isna(autor_musica): autor_musica = 'N/A'
        if pd.isna(link_video): link_video = 'N/A'

        f.write(f"**Categoria:** {categoria} | **Subcategoria:** {subcategoria}\n")
        f.write(f"**Temas Relacionados:** {temas}\n")
        f.write(f"**Textos Relacionados:** {textos_relacionados}\n")
        f.write(f"**Texto Base (Motivador):** {texto_base}\n")
        f.write(f"**Autor da Letra:** {autor_letra} | **Autor da Música:** {autor_musica}\n")
        f.write(f"**Referência em Vídeo:** {link_video}\n\n")
        
        f.write("### Letra do Hino:\n")
        
        # Pega a letra extraída pelo Selenium e garante que seja string
        letra = str(row.get('letra', ''))
        if pd.isna(row.get('letra')) or letra == 'nan': 
            letra = ""
            
        letra_formatada = letra.replace('\n', '\n\n')
        
        f.write(f"{letra_formatada}\n\n")
        f.write("---\n\n")
        
print("Arquivo 'Hinario_NotebookLM.md' gerado com sucesso!")