import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid
import time

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Oncall v17 - NOVA ABA", layout="wide", page_icon="🔥")

# === MUDANÇA DE ESTRATÉGIA: NOVA ABA ===
# Vamos usar uma aba nova para fugir de scripts fantasmas na antiga
ABA_PRINCIPAL = "banco_horas" 
# (Crie essa aba no Google Sheets antes de rodar!)

COLS_OFICIAIS = [
    "id", "data_registro", "colaborador_email", "projeto", "horas", 
    "status_aprovaca", "data_decisao", "competencia", "tipo", 
    "descricão", "email_enviado", "valor_hora_historico"
]

conn = st.connection("gsheets", type=GSheetsConnection)

# --- LEITURA COM DEBUG ---
def carregar():
    try:
        conn.clear()
        try:
            df = conn.read(worksheet=ABA_PRINCIPAL, ttl=0)
        except:
            return pd.DataFrame(columns=COLS_OFICIAIS)

        # Se vier vazio, retorna estrutura vazia
        if df.empty or len(df.columns) < 2:
            return pd.DataFrame(columns=COLS_OFICIAIS)
        
        df.columns = [str(c).strip().lower() for c in df.columns]
        
        # Garante colunas
        for col in COLS_OFICIAIS:
            if col not in df.columns:
                df[col] = ""
                
        return df[COLS_OFICIAIS]
    except Exception as e:
        st.error(f"Erro ao ler: {e}")
        return pd.DataFrame(columns=COLS_OFICIAIS)

df_lan = carregar()

# --- CARREGA CONFIGS (Abas antigas ok) ---
try:
    df_u = conn.read(worksheet="config_usuarios", ttl=0)
    df_p = conn.read(worksheet="config_projetos", ttl=0)
except:
    st.error("Erro nas abas de config. Verifique se existem.")
    st.stop()

# --- DADOS ---
lista_projetos = df_p["projetos"].dropna().astype(str).unique().tolist()
dict_users = {row["emails_autorizados"].strip(): {"valor": row["valor_hora"], "senha": str(row["senhas"]).strip()} for _, row in df_u.dropna(subset=["emails_autorizados"]).iterrows()}
ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

# --- FUNÇÃO SALVAR (SUPER SIMPLES) ---
def salvar(df_final):
    try:
        # VERIFICAÇÃO FINAL ANTES DE MANDAR
        if df_final.empty:
            st.error("ERRO: Tentativa de salvar tabela vazia. Bloqueado.")
            return
            
        conn.clear()
        
        # Prepara
        df_final = df_final[COLS_OFICIAIS] # Ordena
        df_final = df_final.fillna("").astype(str) # Limpa
        
        # Manda bala
        conn.update(worksheet=ABA_PRINCIPAL, data=df_final)
        
        st.success("✅ GRAVADO COM SUCESSO!")
        time.sleep(1); st.rerun()
    except Exception as e:
        st.error(f"❌ ERRO AO GRAVAR: {e}")

# --- LOGIN ---
st.sidebar.header("🔥 OnCall v17")
user = st.sidebar.selectbox("User:", ["..."]+list(dict_users.keys()))
if user == "...": st.stop()
senha = st.sidebar.text_input("Senha:", type="password")
if senha != dict_users[user]["senha"]: st.warning("Senha errada"); st.stop()

# --- INTERFACE ---
t1, t2 = st.tabs(["📝 LANÇAR", "📊 VER DADOS"])

with t1:
    with st.form("f1"):
        c1,c2 = st.columns(2)
        proj = c1.selectbox("Projeto", lista_projetos)
        tipo = c2.selectbox("Tipo", ["Front", "Back", "Infra", "Reunião", "Outros"])
        data = c1.date_input("Data", datetime.now())
        horas = c2.number_input("Horas", step=0.5)
        desc = st.text_area("Descrição")
        
        if st.form_submit_button("GRAVAR AGORA"):
            novo = {
                "id": str(uuid.uuid4()), "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "colaborador_email": user, "projeto": proj, "horas": str(horas),
                "status_aprovaca": "Pendente", "data_decisao": "", "competencia": data.strftime("%Y-%m"),
                "tipo": tipo, "descricão": desc, "email_enviado": "", 
                "valor_hora_historico": str(dict_users[user]["valor"])
            }
            # Adiciona
            df_total = pd.concat([df_lan, pd.DataFrame([novo])], ignore_index=True)
            salvar(df_total)

with t2:
    st.write(f"Lendo da aba: `{ABA_PRINCIPAL}`")
    st.dataframe(df_lan)
    
    # BOTÃO DE PÂNICO PARA RECRIAR CABEÇALHO
    if st.button("🆘 A PLANILHA ZEROU? CLIQUE AQUI"):
        salvar(pd.DataFrame(columns=COLS_OFICIAIS))