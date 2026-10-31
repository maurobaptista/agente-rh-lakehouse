import streamlit as st
import duckdb
import time
from sqlalchemy import create_engine
from langchain_community.utilities import SQLDatabase
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.agent_toolkits import create_sql_agent
import certifi 
import os 

# 1. Configuração Visual da Página
st.set_page_config(page_title="Assistente de RH", page_icon="✨", layout="centered")

# Ocultar branding do Streamlit e aplicar estilo escuro/arredondado
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* A instrução 'header' foi removida para garantir que o botão da barra lateral continua visível */
    
    /* Arredondar a barra de pesquisa de chat */
    .stChatInputContainer {
        border-radius: 25px !important;
        border: 1px solid #444 !important;
        background-color: #212121 !important;
    }
    </style>
    """, unsafe_allow_html=True)

# 2. Criar a Sidebar (Menu Lateral)
with st.sidebar:
    st.markdown("### Your chats")
    st.button("Dashboard RH")
    st.button("Análise de Salários")
    st.button("Contratações Q3")

# 3. Inicializar o Agente
@st.cache_resource
def iniciar_agente():
    os.environ['CURL_CA_INFO'] = certifi.where()
    
    conn = duckdb.connect('meu_lakehouse.duckdb')
    
    conn.execute("INSTALL azure; LOAD azure;")
    conn.execute("INSTALL delta; LOAD delta;")
    conn.execute("SET azure_transport_option_type = 'curl';")
    
    conn.execute(f"""
        CREATE OR REPLACE SECRET sec_azure (
            TYPE AZURE,
            CONNECTION_STRING '{st.secrets["AZURE_STRING"]}'
        );
    """)
    
    conn.execute("DROP TABLE IF EXISTS fact_logs;")
    
    conn.execute("""
        CREATE OR REPLACE TABLE dim_candidato AS
        SELECT * FROM delta_scan('az://gold/dim_candidatos_delta/');
    """)
    
    conn.close() 
    
    db = SQLDatabase.from_uri("duckdb:///meu_lakehouse.duckdb")
    
    llm = ChatGoogleGenerativeAI(
        model="gemini-3.5-flash-lite", 
        google_api_key=st.secrets["GOOGLE_KEY"]
    )
    
    return create_sql_agent(
        llm=llm,
        db=db,
        verbose=True,
        agent_type="zero-shot-react-description",
        agent_executor_kwargs={"handle_parsing_errors": True}
    )

agente = iniciar_agente()

# 4. Gestão da Memória do Chat com Avatares
if "mensagens" not in st.session_state:
    st.session_state.mensagens = []

avatares = {"user": "🧑‍💼", "assistant": "✨"}

# Ecrã de boas-vindas inicial (quando não há mensagens)
if len(st.session_state.mensagens) == 0:
    st.markdown("<h2 style='text-align: center; color: white; margin-top: 15vh; margin-bottom: 15vh;'>Good to see you.</h2>", unsafe_allow_html=True)

# Carregar histórico de mensagens
for msg in st.session_state.mensagens:
    with st.chat_message(msg["role"], avatar=avatares.get(msg["role"])):
        st.markdown(msg["content"])

# Função para simular o efeito de digitação do ChatGPT
def stream_texto(texto):
    for palavra in texto.split(" "):
        yield palavra + " "
        time.sleep(0.04)

# 5. Input do Utilizador e Execução
pergunta = st.chat_input("Ask anything")

if pergunta:
    # Mostrar pergunta do utilizador
    st.session_state.mensagens.append({"role": "user", "content": pergunta})
    with st.chat_message("user", avatar=avatares["user"]):
        st.markdown(pergunta)
        
    # --- A MAGIA DA NUVEM NO LUGAR DO AVATAR (.GIF) ---
    # Usamos o teu ficheiro "nuvem.gif" como avatar durante a geração da resposta
    with st.chat_message("assistant", avatar="nuvem.gif"):
        espaco_resposta = st.empty()
        espaco_resposta.markdown("A pensar...")
        
        # O agente processa a resposta "por trás das cortinas"
        try:
            resposta = agente.invoke({"input": pergunta})
            texto_final = resposta['output']
        except Exception as e:
            texto_final = f"Ocorreu um erro durante a análise: {e}"
            
        # Quando o agente tem a resposta pronta, limpamos o "A pensar..."
        espaco_resposta.empty()
        
        # E mostramos a resposta final a escrever letra a letra
        espaco_resposta.write_stream(stream_texto(texto_final))
        
    # Guarda a resposta no histórico (as mensagens antigas voltarão a ter o avatar normal da estrela)
    st.session_state.mensagens.append({"role": "assistant", "content": texto_final})