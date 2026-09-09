from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
BASES_DIR = ROOT_DIR / "basesdedados"

import pandas as pd
import json
import sqlite3

print("Iniciando o cruzamento de dados...")

# 1. Carregar o CSV com os metadados (autores, categorias, links)
df_metadados = pd.read_csv(BASES_DIR / 'BD_Hinario_Final_Completo.csv') # Substitua pelo nome do seu CSV mais recente

# 2. Carregar o JSON com as letras que extraímos anteriormente
with open(ROOT_DIR / 'Ideia' / 'hinario_completo.json', 'r', encoding='utf-8') as f:
    dados_letras = json.load(f)

# 3. Transformar o JSON de letras em um DataFrame
# O JSON possui "numero_indice", "titulo" e "letra"
df_letras = pd.DataFrame(dados_letras)

# Renomear a coluna para bater com o CSV e facilitar o merge
df_letras.rename(columns={'numero_indice': 'Número'}, inplace=True)
df_letras['Número'] = df_letras['Número'].astype(str).str.strip()
# Remover a coluna 'titulo' do df_letras se ela já existir no CSV de metadados para evitar duplicatas
if 'titulo' in df_letras.columns:
    df_letras.drop(columns=['titulo'], inplace=True)

# 4. Fazer o Merge (Cruzamento) usando a coluna 'Número'
df_final = pd.merge(df_metadados, df_letras, on='Número', how='left')

# 5. Exportar para CSV (Para o seu controle/backup)
df_final.to_csv(BASES_DIR / 'BD_Hinario_Master.csv', index=False, encoding='utf-8')
print("CSV Master gerado com sucesso!")

# 6. Exportar DIRETAMENTE para SQLite (Para usar no app Flet!)
# Isso cria o arquivo do banco de dados e uma tabela chamada 'hinos'
conexao = sqlite3.connect(BASES_DIR / 'hinario_app.db')
df_final.to_sql('hinos', conexao, if_exists='replace', index=False)
conexao.close()

print("Banco de dados 'hinario_app.db' gerado com sucesso e pronto para o Flet!")