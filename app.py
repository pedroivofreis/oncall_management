import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid
import time

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="OnCall v24 - Cache Shield", layout="wide", page_icon="🛡️")

# === ESTRUTURA IMUTÁVEL ===
ABA_PRINCIPAL = "banco_horas" 
COLS_OFICIAIS = [
    "id", "data_registro", "colaborador_email", "projeto", "horas", 
    "status_aprovaca", "data_decisao", "competencia", "tipo", 
    "descricão", "email_enviado", "valor_hora_historico"
]

conn = st.connection("gsheets", type=GSheetsConnection)

# --- 1. LEITURA COM FILTRO DE CACHE ---
def carregar_dados_seguros():
    # Forçamos o Streamlit a esquecer TUDO o que ele acha que sabe sobre a planilha
    st.cache_data.clear() 
    conn.clear()
    
    try:
        df = conn.read(worksheet=ABA_PRINCIPAL, ttl=0)
        
        if df is None or df.empty or len(df.columns) < 2:
            return pd.DataFrame(columns=COLS_OFICIAIS)
        
        df.columns = [str(c).strip().lower() for c in df.columns]
        
        # Se a leitura falhar em trazer as colunas, não aceitamos "vazio"
        if "projeto" not in df.columns:
            return pd.DataFrame(columns=COLS_OFICIAIS)
            
        return df[COLS_OFICIAIS]
    except Exception:
        return pd.DataFrame(columns=COLS_OFICIAIS)

# --- 2. SALVAMENTO COM DELAY DE CONFIRMAÇÃO ---
def salvar_blindado(df_para_gravar):
    try:
        if df_para_gravar is None or df_para_gravar.empty:
            # Nunca permitimos salvar um DataFrame totalmente vazio que mataria o cabeçalho
            df_para_gravar = pd.DataFrame(columns=COLS_OFICIAIS)

        # Re-garante as colunas no DF de saída
        for col in COLS_OFICIAIS:
            if col not in df_para_gravar.columns:
                df_para_gravar[col] = ""
        
        df_final = df_para_gravar[COLS_OFICIAIS].fillna("").astype(str)

        # --- A MANOBRA DE SEGURANÇA ---
        with st.spinner("📦 Sincronizando com Google Sheets (Aguarde 2s)..."):
            conn.update(worksheet=ABA_PRINCIPAL, data=df_final)
            # Damos 2 segundos para o Google Sheets "respirar" e consolidar os dados
            time.sleep(2) 
            conn.clear()
            st.cache_data.clear()

        st.toast("✅ Sincronizado!", icon="🚀")
        time.sleep(0.5)
        st.rerun()
        
    except Exception as e:
        st.error(f"❌ Erro: {e}")

# --- 3. LOGIN ---
dict_users = {
    "pedroivofernandesreis@gmail.com": {"valor": 100, "senha": "123"},
    "claudiele.andrade@gmail.com": {"valor": 150, "senha": "456"}
}
lista_projs = ["Sustentação", "Projeto A", "Projeto B", "Consultoria", "Outros"]

st.sidebar.title("🛡️ OnCall v24")
user = st.sidebar.selectbox("Usuário", ["..."] + list(dict_users.keys()))
if user == "...": st.stop()
senha = st.sidebar.text_input("Senha", type="password")
if senha != dict_users[user]["senha"]: st.stop()

# --- 4. CARREGAMENTO ---
df_lan = carregar_dados_seguros()

# --- 5. INTERFACE ---
t1, t2, t3 = st.tabs(["📝 LANÇAR", "🛡️ ADMIN", "📊 DASH"])

with t1:
    with st.form("f_novo"):
        st.markdown("### Registrar Horas")
        c1, c2 = st.columns(2)
        p = c1.selectbox("Projeto", lista_projs)
        t = c2.selectbox("Tipo", ["Front-end", "Back-end", "Infra", "Reunião"])
        d = c1.date_input("Data", datetime.now())
        h = c2.number_input("Horas", min_value=0.5, step=0.5)
        desc = st.text_area("Descrição")
        
        if st.form_submit_button("GRAVAR REGISTRO"):
            novo = {
                "id": str(uuid.uuid4()), "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "colaborador_email": user, "projeto": p, "horas": str(h),
                "status_aprovaca": "Pendente", "data_decisao": "", "competencia": d.strftime("%Y-%m"),
                "tipo": t, "descricão": desc, "email_enviado": "", 
                "valor_hora_historico": str(dict_users[user]["valor"])
            }
            df_atualizado = pd.concat([df_lan, pd.DataFrame([novo])], ignore_index=True)
            salvar_blindado(df_atualizado)

with t2:
    if user in ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]:
        with st.form("f_adm"):
            st.info("Edite os dados e clique em salvar. O sistema aguardará a confirmação do Google.")
            df_editado = st.data_editor(df_lan, num_rows="dynamic", use_container_width=True)
            if st.form_submit_button("💾 SALVAR ALTERAÇÕES"):
                salvar_blindado(df_editado)

with t3:
    st.dataframe(df_lan[df_lan["colaborador_email"] == user], use_container_width=True)

# --- BOTÃO DE EMERGÊNCIA ---
st.sidebar.divider()
if st.sidebar.button("🆘 FORÇAR CABEÇALHO"):
    salvar_blindado(pd.DataFrame(columns=COLS_OFICIAIS))