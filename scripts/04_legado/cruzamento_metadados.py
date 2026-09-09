from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
BASES_DIR = ROOT_DIR / "basesdedados"

import os
import json
import pandas as pd
import re

print("Iniciando o cruzamento de metadados e limpeza de textos...")

# 1. Carregar os dicionários de mapeamento
def carregar_mapeamento(caminho_arquivo, chave_lista):
    with open(caminho_arquivo, 'r', encoding='utf-8') as f:
        dados = json.load(f)
    return {item['id']: item for item in dados[chave_lista]}

autores_dict = carregar_mapeamento(str(BASES_DIR / 'autores.json'), 'authors')
categorias_dict = carregar_mapeamento(str(BASES_DIR / 'categorias.json'), 'categories')
subcat_dict = carregar_mapeamento(str(BASES_DIR / 'subcategorias.json'), 'subcategories')

# 2. Ler o CSV original forçando a coluna 'Número' como texto
# (Substitua 'BD_Hinario_Metadados_com_Links.csv' pelo nome correto se você o renomeou)
df_csv = pd.read_csv(BASES_DIR / 'BD_Hinario_Metadados_com_Links.csv', dtype={'Número': str})
df_csv['Número'] = df_csv['Número'].str.strip() 

# Renomeia a coluna no DataFrame (se ela já não se chamar "Textos Relacionados")
if 'Textos Bíblicos Base' in df_csv.columns:
    df_csv.rename(columns={'Textos Bíblicos Base': 'Textos Relacionados'}, inplace=True)

# 3. Preparar a extração
dados_extraidos = []
pasta_hinos = str(ROOT_DIR / 'hinos_json')

for nome_arquivo in os.listdir(pasta_hinos):
    if nome_arquivo.endswith('.json'):
        caminho_hino = os.path.join(pasta_hinos, nome_arquivo)
        
        with open(caminho_hino, 'r', encoding='utf-8') as f:
            dados_hino = json.load(f)['hymn']
            
            # Pega o número como string (Evita o erro do 587A)
            numero_hino = str(dados_hino['number']).strip()
            
            # Pega o 'verse' do JSON que será a nossa nova coluna "Texto Base"
            texto_base = dados_hino.get('verse', '') 
            
            # Cruzar Subcategoria e Categoria
            id_subcat = dados_hino.get('subCategory')
            nome_subcat = ""
            nome_categoria = ""
            
            if id_subcat and id_subcat in subcat_dict:
                nome_subcat = subcat_dict[id_subcat]['name']
                id_cat = subcat_dict[id_subcat]['category']
                if id_cat in categorias_dict:
                    nome_categoria = categorias_dict[id_cat]['name']
            
            # Cruzar Autores
            def obter_nomes_autores(lista_ids):
                nomes = [autores_dict[id_autor]['name'] for id_autor in lista_ids if id_autor in autores_dict]
                return ", ".join(nomes) if nomes else "Desconhecido"
            
            autor_letra = obter_nomes_autores(dados_hino.get('lyricsComposer', []))
            autor_musica = obter_nomes_autores(dados_hino.get('musicComposer', []))
            
            dados_extraidos.append({
                'Número': numero_hino,
                'Texto Base': texto_base,
                'Categoria': nome_categoria,
                'Subcategoria': nome_subcat,
                'Autor da Letra': autor_letra,
                'Autor da Música': autor_musica
            })

# 4. Transformar em DataFrame e fazer o Merge
df_novos_dados = pd.DataFrame(dados_extraidos)
df_final = pd.merge(df_csv, df_novos_dados, on='Número', how='left')

# 5. LÓGICA DE LIMPEZA: O Verificador de Textos
def limpar_textos_relacionados(row):
    base = str(row.get('Texto Base', '')).strip()
    relacionados = str(row.get('Textos Relacionados', '')).strip()

    # Se ambos existirem e não forem nulos ou vazios
    if base and base.lower() != 'nan' and relacionados and relacionados.lower() != 'nan':
        # Verifica se o texto base está DENTRO dos textos relacionados
        if base in relacionados:
            # Substitui a ocorrência exata do Texto Base por nada
            relacionados = relacionados.replace(base, '')
            
            # LIMPEZA COM REGEX: 
            # Como a remoção pode deixar barras "|" ou pontos e vírgulas ";" sobrando...
            
            # 1. Remove qualquer " | | " ou " ; ; " duplo que tenha sobrado no meio
            relacionados = re.sub(r'([;|]\s*)+', r'\1', relacionados) 
            
            # 2. Remove "|" ou ";" soltos no começo da string
            relacionados = re.sub(r'^[\s;|]+', '', relacionados)      
            
            # 3. Remove "|" ou ";" soltos no final da string
            relacionados = re.sub(r'[\s;|]+$', '', relacionados)      
            
    # Se sobrou apenas espaços vazios após a limpeza, devolve "N/A"
    return relacionados.strip() if relacionados.strip() and relacionados.lower() != 'nan' else "N/A"

# Aplica a função de limpeza, linha por linha
df_final['Textos Relacionados'] = df_final.apply(limpar_textos_relacionados, axis=1)

# Preenche vazios do Texto Base com "N/A" para o app não engasgar com valores nulos
df_final['Texto Base'] = df_final['Texto Base'].fillna('N/A')
df_final.loc[df_final['Texto Base'] == '', 'Texto Base'] = 'N/A'

# 6. Salvar o CSV Final
df_final.to_csv(BASES_DIR / 'BD_Hinario_Final_Completo.csv', index=False, encoding='utf-8')

print("Processamento concluído! O arquivo 'BD_Hinario_Final_Completo.csv' está pronto para ir pro Script 2.")