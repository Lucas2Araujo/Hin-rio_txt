import json
import re
from pathlib import Path

# 1. Definir os caminhos dos arquivos dinamicamente na pasta do script
ROOT_DIR = Path(__file__).resolve().parent.parent.parent

arquivo_md = ROOT_DIR / "Textos" / "Hinario_NotebookLM.md"
arquivo_json_curado = ROOT_DIR / "Textos" / "textos_relacionados.json"
arquivo_saida = ROOT_DIR / "Ideia" / "hinario_completo.json"

print(f"[*] Diretório de trabalho: {BASE_DIR}")

# 2. Carregar o JSON com a curadoria de textos relacionados
textos_curados_map = {}
if arquivo_json_curado.exists():
    try:
        with open(arquivo_json_curado, "r", encoding="utf-8") as f:
            dados_curados = json.load(f)
            
        for item in dados_curados:
            numero_key = str(item.get("numero", "")).strip()
            # Limpa possíveis tags de citação (ex: [cite: 1])
            textos_limpos = [
                re.sub(r'\[cite:[^\]]+\]', '', t).strip()
                for t in item.get("textos_relacionados", [])
            ]
            item_copia = dict(item)
            item_copia["textos_relacionados"] = textos_limpos
            textos_curados_map[numero_key] = item_copia
            
        print(f"[✓] {len(textos_curados_map)} registros de textos relacionados carregados de '{arquivo_json_curado.name}'.")
    except Exception as e:
        print(f"[!] Erro ao carregar '{arquivo_json_curado.name}': {e}")
else:
    print(f"[!] Aviso: Arquivo '{arquivo_json_curado.name}' não encontrado em {BASE_DIR}")

# 3. Extrair todos os metadados e a formatação completa do arquivo Markdown
hinario_db = []

if not arquivo_md.exists():
    print(f"[Erro] Arquivo '{arquivo_md.name}' não foi encontrado em {BASE_DIR}!")
else:
    with open(arquivo_md, "r", encoding="utf-8") as f:
        md_content = f.read()

    # Divide o documento pelos blocos de hinos
    hinos_raw = re.split(r'\n## Hino ', md_content)[1:]

    for hino_text in hinos_raw:
        lines = hino_text.strip().split('\n')
        if not lines:
            continue

        # Extrair Número e Título do cabeçalho
        match_header = re.match(r'([0-9_AB]+):\s*(.*)', lines[0])
        if not match_header:
            continue

        numero_str = match_header.group(1).strip()
        titulo = match_header.group(2).strip()

        # Converter para int se for puramente numérico (ex: 1, 2) ou manter str (ex: 587_A)
        try:
            numero = int(numero_str)
        except ValueError:
            numero = numero_str

        # Extrair Categoria e Subcategoria
        match_cat = re.search(r'\*\*Categoria:\*\*\s*(.*?)\s*\|\s*\*\*Subcategoria:\*\*\s*(.*)', hino_text)
        categoria = match_cat.group(1).strip() if match_cat else ""
        subcategoria = match_cat.group(2).strip() if match_cat else ""
        if categoria.lower() in ("nan", "n/a"):
            categoria = ""
        if subcategoria.lower() in ("nan", "n/a"):
            subcategoria = ""

        # Extrair Temas Relacionados
        match_temas = re.search(r'\*\*Temas Relacionados:\*\*\s*(.*)', hino_text)
        temas_raw = match_temas.group(1).strip() if match_temas else ""
        if temas_raw.lower() in ("nan", "n/a", ""):
            temas = []
        else:
            temas = [t.strip() for t in temas_raw.split('|') if t.strip()]

        # Extrair Texto Base (Motivador)
        match_base = re.search(r'\*\*Texto Base \(Motivador\):\*\*\s*(.*)', hino_text)
        texto_base = match_base.group(1).strip() if match_base else ""
        if texto_base.lower() in ("nan", "n/a"):
            texto_base = ""

        # Extrair Autores
        match_autores = re.search(r'\*\*Autor da Letra:\*\*\s*(.*?)\s*\|\s*\*\*Autor da Música:\*\*\s*(.*)', hino_text)
        autor_letra = match_autores.group(1).strip() if match_autores else ""
        autor_musica = match_autores.group(2).strip() if match_autores else ""
        if autor_letra.lower() in ("nan", "n/a"):
            autor_letra = ""
        if autor_musica.lower() in ("nan", "n/a"):
            autor_musica = ""

        # Extrair Link de Vídeo
        match_video = re.search(r'\*\*Referência em Vídeo:\*\*\s*(.*)', hino_text)
        link_video = match_video.group(1).strip() if match_video else ""
        if link_video.lower() in ("nan", "n/a"):
            link_video = ""

        # Extrair Letra Completa do Hino
        if '### Letra do Hino:' in hino_text:
            letra_part = hino_text.split('### Letra do Hino:')[1]
            # Remove o separador final '---' e espaços extras
            letra = re.sub(r'\n+---\s*$', '', letra_part).strip()
        else:
            letra = ""

        # Obter textos relacionados do JSON curado (ou dados adicionais caso existam)
        curado_info = textos_curados_map.get(str(numero), {})
        textos_relacionados = curado_info.get("textos_relacionados", [])

        # Se o texto base estiver vazio no MD mas existir no JSON curado, utiliza-o
        if not texto_base and curado_info.get("texto_base"):
            texto_base = curado_info.get("texto_base").strip()

        # Montar o objeto completo no formato JSON estruturado com todos os dados do MD + JSON
        hino_obj = {
            "numero": numero,
            "titulo": titulo,
            "categoria": categoria,
            "subcategoria": subcategoria,
            "temas_relacionados": temas,
            "texto_base": texto_base,
            "textos_relacionados": textos_relacionados,
            "autor_letra": autor_letra,
            "autor_musica": autor_musica,
            "link_video": link_video,
            "letra": letra
        }
        hinario_db.append(hino_obj)

    print(f"[✓] {len(hinario_db)} hinos processados do arquivo Markdown.")

# 4. Salvar o arquivo JSON unificado e formatado
if hinario_db:
    with open(arquivo_saida, "w", encoding="utf-8") as f:
        json.dump(hinario_db, f, ensure_ascii=False, indent=2)

    print(f"[✓] Sucesso! Base de dados completa exportada para '{arquivo_saida.name}' ({len(hinario_db)} hinos).")
else:
    print("[!] Nenhum hino foi processado para salvar.")