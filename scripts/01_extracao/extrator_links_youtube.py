from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
INPUT_CSV = ROOT_DIR / "basesdedados" / "BD_Hinario_Metadados.csv"
OUTPUT_CSV = ROOT_DIR / "basesdedados" / "BD_Hinario_Metadados_com_Links.csv"

import yt_dlp
import pandas as pd
import unicodedata
import re

# Função para remover acentos e transformar tudo em minúsculas
def normalizar_texto(texto):
    if pd.isna(texto) or texto is None or str(texto).strip() == 'None':
        return ""
    texto = str(texto).lower()
    return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')

# Suas playlists em ordem
playlists = [
    "https://youtube.com/playlist?list=PLAPpcKnpMfeO9Fydpl1tTKC9CRRnIMMSK",
    "https://youtube.com/playlist?list=PLAPpcKnpMfeOsWzlaY0bXm1Q5pnQQxn_y",
    "https://youtube.com/playlist?list=PLAPpcKnpMfeMnCMuGcdWKVkgpi2P_sRkE",
    "https://youtube.com/playlist?list=PLAPpcKnpMfeNIrE1nk3w2OkcUdxuY6y1l",
    "https://youtube.com/playlist?list=PLAPpcKnpMfePvD6DLI-Y5TR-RVVo62s6Z",
    "https://youtube.com/playlist?list=PLAPpcKnpMfePWEOuIu4B4F3PVljyD8DoO"
]

# Configuração do yt-dlp para extrair título e URL sem baixar
opcoes_ydl = {'extract_flat': True, 'quiet': True}
videos_extraidos = []

print("Extraindo links e títulos das playlists... Isso pode levar alguns segundos.")
with yt_dlp.YoutubeDL(opcoes_ydl) as ydl:
    for url in playlists:
        info = ydl.extract_info(url, download=False)
        if 'entries' in info:
            for video in info['entries']:
                titulo = video.get('title', '')
                
                # Filtro crucial: Ignora vídeos privados, deletados ou indisponíveis (None)
                if titulo and str(titulo) not in ['[Private video]', '[Deleted video]', 'None']:
                    videos_extraidos.append({
                        'url': video.get('url'),
                        'titulo_youtube': str(titulo)
                    })

# Carrega o seu CSV original
df = pd.read_csv(INPUT_CSV)

links_finais = []
avisos = []

print("\nIniciando validação e cruzamento inteligente dos dados...\n")

# Compara buscando pelo conteúdo e não pela ordem
for index, row in df.iterrows():
    numero_csv = str(row['Número'])
    titulo_csv = normalizar_texto(row['Título'])
    
    # Prepara o número para buscar exatamente ele no título do YouTube (ex: " 509 " isolado)
    numero_limpo = numero_csv.replace("_", "").lower()
    padrao_numero = re.compile(rf'\b{numero_limpo}\b')
    
    # Prepara as palavras do título do hino
    palavras_titulo = titulo_csv.split()
    palavras_chave = [p for p in palavras_titulo if len(p) > 2][:2]

    video_encontrado = None
    
    # Procura o vídeo correspondente na lista extraída
    for i, video in enumerate(videos_extraidos):
        titulo_yt = normalizar_texto(video['titulo_youtube'])
        
        # 1. Checa se o número isolado aparece no título (ex: encontra "509" mas ignora "5090")
        match_numero = bool(padrao_numero.search(titulo_yt))
        
        # 2. Checa se as palavras principais aparecem no título
        match_nome = False
        if palavras_chave and all(palavra in titulo_yt for palavra in palavras_chave):
            match_nome = True
            
        if match_numero or match_nome:
            video_encontrado = video
            # Remove o vídeo encontrado da lista para não repetir em outro hino acidentalmente
            videos_extraidos.pop(i)
            break

    # Adiciona o link correto ou gera um aviso se realmente não existir
    if video_encontrado:
        links_finais.append(video_encontrado['url'])
    else:
        links_finais.append(None)
        avisos.append(f"[!] Vídeo não encontrado para o hino {numero_csv} ('{row['Título']}')")

# Salva o novo arquivo sobrescrevendo a versão com erro
df['Link do Vídeo'] = links_finais
df.to_csv(OUTPUT_CSV, index=False)

# Exibe o resultado final
if avisos:
    print("O arquivo foi salvo, mas os seguintes hinos ficaram sem link (talvez não estejam nas playlists):")
    for aviso in avisos:
        print(aviso)
else:
    print("Sucesso total! Todos os 601 vídeos foram vinculados corretamente aos hinos.")
    
print("\nArquivo 'BD_Hinario_Metadados_com_Links.csv' gerado com sucesso!")