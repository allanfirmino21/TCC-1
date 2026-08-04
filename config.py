# config.py

# Modelo da Google usado para geração de texto; flash oferece boa velocidade sem abrir mão de qualidade
MODELO_LLM           = "gemini-2.5-flash"

# Modelo Pro da Google; usado em avaliações comparativas de qualidade vs. o Flash padrão
MODELO_LLM_PRO       = "gemini-2.5-pro"

# Modelo sentence-transformers para gerar embeddings; versão multilingual cobre português nativamente
MODELO_EMBEDDINGS    = "paraphrase-multilingual-mpnet-base-v2"

# Limite legado mantido para não quebrar chamadas antigas; novos prompts usam as constantes abaixo
MAX_TOKENS_LLM       = 1000

# Limite para o Prompt 1 (extração de dados em JSON estruturado); valor alto para acomodar documentos longos
MAX_TOKENS_EXTRACAO  = 8192

# Limite para o Prompt 2 (geração da narrativa em 7 seções); alto o suficiente para texto analítico completo
MAX_TOKENS_NARRATIVA = 8192

# Número máximo de chunks numéricos (tabelas/valores) recuperados no RAG; 3 equilibra precisão e custo de contexto
MAX_CHUNKS_NUMERICO  = 3

# Número máximo de chunks narrativos (texto discursivo) recuperados no RAG; 2 evita ruído em análises qualitativas
MAX_CHUNKS_NARRATIVO = 2

# Tamanho máximo de cada chunk em palavras; 800 cabe confortavelmente no contexto sem truncar ideias
MAX_PALAVRAS_CHUNK   = 800

# Sobreposição entre chunks consecutivos em palavras; 100 garante continuidade de frases nos limites
OVERLAP_PALAVRAS     = 100

# URL raiz do portal de dados abertos da CVM onde ficam os documentos das companhias abertas
BASE_URL_CVM         = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC"

# Pasta local onde os arquivos baixados da CVM são armazenados para evitar downloads repetidos
CAMINHO_CACHE        = "dados/cache"

# Diretório do banco vetorial ChromaDB; separado dos dados brutos para facilitar reset independente
CAMINHO_CHROMA       = "chroma_db"

# CSV com metadados das companhias (CNPJ, nome, setor etc.) obtido da CVM e usado como índice de consulta
TABELA_CVM           = "dados/tabela_cvm.csv"
