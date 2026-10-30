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

# Ocultar branding do Streamlit e melhorar margens (Visual Profissional)
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

st.title("✨ Portal de Analytics de RH")
st.write("Faça perguntas em linguagem natural sobre os dados do Lakehouse.")

# 2. Inicializar o Agente (Ligação ao Azure ADLS Gen2 via DuckDB)
@st.cache_resource
def iniciar_agente():
    
    # 1. O truque definitivo: Forçar o sistema operativo a ver o certificado
    os.environ['SSL_CERT_FILE'] = certifi.where()
    
    conn = duckdb.connect('meu_lakehouse.duckdb')
    
    # A linha mágica que resolve o erro de SSL no Streamlit Cloud
    conn.execute(f"SET ca_cert_file='{certifi.where()}';") 
    
    conn.execute("INSTALL azure; LOAD azure;")
    conn.execute("INSTALL delta; LOAD delta;")
    
    # Autenticação com a Connection String via st.secrets
    conn.execute(f"""
        CREATE OR REPLACE SECRET sec_azure (
            TYPE AZURE,
            CONNECTION_STRING '{st.secrets["AZURE_STRING"]}'
        );
    """)
    
    # Limpa tudo antes de criar para evitar conflitos
    conn.execute("DROP TABLE IF EXISTS dim_candidato;")
    conn.execute("DROP TABLE IF EXISTS fact_logs;")

    # Cria as tabelas físicas lendo o Delta Lake com o prefixo az://
    conn.execute("""
        CREATE TABLE dim_candidato AS 
        SELECT * FROM delta_scan('az://gold/dim_candidatos_delta/');
    """)
    conn.execute("""
        CREATE TABLE fact_logs AS 
        SELECT * FROM delta_scan('az://gold/fact_logs_delta/');
    """)
    conn.close()

    # Conectar o LangChain via SQLAlchemy
    engine = create_engine("duckdb:///meu_lakehouse.duckdb")
    db = SQLDatabase(
        engine=engine,
        include_tables=["dim_candidato", "fact_logs"],
        view_support=False
    )
    
    llm = ChatGoogleGenerativeAI(
        model="gemini-3.5-flash-lite", 
        google_api_key=st.secrets["GOOGLE_KEY"]
    )
    
    return create_sql_agent(
        llm=llm, 
        db=db, 
        verbose=True,  # Mudámos para True para veres o pensamento dele no terminal
        agent_type="zero-shot-react-description", 
        max_iterations=20,  # Aumentámos de 10 para 20 tentativas
        agent_executor_kwargs={"handle_parsing_errors": True}
    )

agente = iniciar_agente()

# 3. Gestão da Memória do Chat com Avatares
if "mensagens" not in st.session_state:
    st.session_state.mensagens = []

# Dicionário de ícones para o chat
avatares = {"user": "🧑‍💼", "assistant": "✨"}

for msg in st.session_state.mensagens:
    with st.chat_message(msg["role"], avatar=avatares.get(msg["role"])):
        st.markdown(msg["content"])

# Função para simular o efeito de digitação do ChatGPT
def stream_texto(texto):
    for palavra in texto.split(" "):
        yield palavra + " "
        time.sleep(0.04)

# 4. Input do Utilizador
pergunta = st.chat_input("Pergunte algo aos dados de RH...")

# 5. Execução com Efeito "A pensar..." expansível
if pergunta:
    st.session_state.mensagens.append({"role": "user", "content": pergunta})
    with st.chat_message("user", avatar=avatares["user"]):
        st.markdown(pergunta)
        
    with st.chat_message("assistant", avatar=avatares["assistant"]):
        # A caixa de status simula o painel "Thinking" da IA
        with st.status("A analisar a estrutura do Lakehouse...", expanded=True) as status:
            st.write("A interpretar a pergunta...")
            try:
                resposta = agente.invoke({"input": pergunta})
                texto_final = resposta['output']
                status.update(label="Análise concluída!", state="complete", expanded=False)
            except Exception as e:
                status.update(label="Erro durante a análise", state="error", expanded=False)
                st.error(f"Detalhe do erro: {e}")
                st.stop()
        
        # Escreve a resposta final letra a letra
        st.write_stream(stream_texto(texto_final))
        st.session_state.mensagens.append({"role": "assistant", "content": texto_final})


