from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent

import json
import time
import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

# 1. Carregando variáveis de ambiente
load_dotenv(ROOT_DIR / ".env")
CHAVE_API = os.getenv("AIStudiokey")

# Validação para impedir o Erro 401 antes mesmo de chamar a rede
if not CHAVE_API:
    raise ValueError("Erro: Chave da API não encontrada. Verifique se o arquivo .env está na mesma pasta do script e se o nome da variável é AIStudiokey.")

# 2. Inicializando o novo cliente da API
client = genai.Client(api_key=CHAVE_API)

# Usando o modelo que você definiu
MODELO = 'gemini-3.5-flash'

def buscar_referencias(hino):
    prompt = f"""
    Você é um teólogo especialista em referências cruzadas da Bíblia.
    Preciso de 3 a 5 textos bíblicos fortemente relacionados ao seguinte hino:
    - Categoria: {hino['categoria']}
    - Subcategoria: {hino['subcategoria']}
    - Texto Base: {hino['texto_base_motivador']}
    
    Atenção: Utilize exclusivamente a tradução Almeida Revista e Atualizada (ARA) como base para a sua análise semântica e teológica.
    
    RETORNE APENAS UM ARRAY JSON VÁLIDO contendo as referências no formato "Livro Capítulo:Versículo".
    Exemplo de saída desejada: ["João 3:16", "Romanos 5:8", "Êxodo 20:8-11"]
    """
    
    try:
        # Nova sintaxe de chamada usando o SDK atualizado
        response = client.models.generate_content(
            model=MODELO,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json", # Força a IA a devolver um JSON limpo
                temperature=0.2 # Reduz a "criatividade" para garantir formatação rigorosa
            ),
        )
        
        # Como forçamos o mime_type, o text já vem como um JSON perfeito
        referencias = json.loads(response.text)
        return referencias
    except Exception as e:
        print(f"Erro ao processar o hino {hino['numero']}: {e}")
        return []

# 3. Lendo o banco de dados original
ARQUIVO_JSON = ROOT_DIR / "basesdedados" / "hinario_indexado.json"

with open(ARQUIVO_JSON, "r", encoding="utf-8") as f:
    hinos = json.load(f)

print("Iniciando a geração de referências cruzadas...")

# 4. Limitando aos 5 primeiros hinos para teste
for hino in hinos[:5]:
    
    # Pula hinos que já foram processados
    if len(hino.get("textos_relacionados", [])) > 0:
        print(f"Hino {hino['numero']} já possui referências. Pulando...")
        continue
        
    print(f"Analisando Hino {hino['numero']} (Texto base: {hino['texto_base_motivador']})...")
    
    # Busca e injeta as referências
    hino["textos_relacionados"] = buscar_referencias(hino)
    
    # 5. Salvamento Iterativo
    with open(ARQUIVO_JSON, "w", encoding="utf-8") as f:
        json.dump(hinos, f, ensure_ascii=False, indent=4)
        
    # Pausa para respeitar os limites da API (Rate Limit)
    time.sleep(4)

print("\nProcesso concluído! Verifique o arquivo 'hinario_indexado.json'.")