import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid
import time

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="OnCall v23 - Anti-Wipe", layout="wide", page_icon="🛡️")

# === DEFINIÇÃO IMUTÁVEL ===
ABA_PRINCIPAL = "banco_horas" 
COLS_OFICIAIS = [
    "id", "data_registro", "colaborador_email", "projeto", "horas", 
    "status_aprovaca", "data_decisao", "competencia", "tipo", 
    "descricão", "email_enviado", "valor_hora_historico"
]

conn = st.connection("gsheets", type=GSheetsConnection)

# --- 1. FUNÇÃO DE LEITURA (COM GARANTIA DE CABEÇALHO) ---
def carregar_dados_seguros():
    try:
        conn.clear()
        df = conn.read(worksheet=ABA_PRINCIPAL, ttl=0)
        
        if df.empty or len(df.columns) < 2:
            return pd.DataFrame(columns=COLS_OFICIAIS)
        
        # Normaliza nomes das colunas
        df.columns = [str(c).strip().lower() for c in df.columns]
        
        # Se as colunas lidas estiverem erradas, ignora e força as oficiais
        for col in COLS_OFICIAIS:
            if col not in df.columns:
                df[col] = ""
        
        return df[COLS_OFICIAIS]
    except Exception:
        return pd.DataFrame(columns=COLS_OFICIAIS)

# --- 2. FUNÇÃO DE SALVAMENTO (O MOTOR BLINDADO) ---
def salvar_master(df_para_gravar):
    """
    Esta função garante que o cabeçalho NUNCA seja esquecido 
    no momento do upload para o Google Sheets.
    """
    try:
        if df_para_gravar is None:
            return

        # PASSO A: Garantir que o DataFrame de envio tenha TODAS as colunas oficiais
        for col in COLS_OFICIAIS:
            if col not in df_para_gravar.columns:
                df_para_gravar[col] = ""
        
        # PASSO B: Forçar a ordem exata (isso reconstrói o cabeçalho na linha 1)
        df_final = df_para_gravar[COLS_OFICIAIS].copy()
        
        # PASSO C: Limpeza de dados (converte nulos em vazio e tudo para texto)
        df_final = df_final.fillna("").astype(str)
        
        # PASSO D: O envio final
        conn.clear()
        conn.update(worksheet=ABA_PRINCIPAL, data=df_final)
        
        st.toast("✅ Dados sincronizados com sucesso!", icon="🎉")
        time.sleep(1)
        st.rerun()
        
    except Exception as e:
        st.error(f"❌ ERRO AO GRAVAR: {e}")
        if "protected" in str(e).lower():
            st.warning("⚠️ Remova a proteção da Linha 1 no Google Sheets!")

# --- 3. LOGIN E CONFIGS ---
dict_users = {
    "pedroivofernandesreis@gmail.com": {"valor": 100, "senha": "123"},
    "claudiele.andrade@gmail.com": {"valor": 150, "senha": "456"}
}
lista_projs = ["Sustentação", "Projeto A", "Projeto B", "Consultoria", "Outros"]
ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

st.sidebar.title("🚀 OnCall Phoenix")
user = st.sidebar.selectbox("Usuário", ["Selecione..."] + list(dict_users.keys()))

if user == "Selecione...":
    st.stop()

senha = st.sidebar.text_input("Senha", type="password")
if senha != dict_users[user]["senha"]:
    st.stop()

# --- 4. CARREGAMENTO DOS DADOS ---
df_lan = carregar_dados_seguros()

# --- 5. INTERFACE (TABS) ---
t_lancar, t_dash, t_admin, t_bi = st.tabs(["📝 LANÇAR", "📊 MEU DASH", "🛡️ ADMIN", "📈 BI"])

with t_lancar:
    with st.form("form_novo"):
        st.markdown("### Registrar Horas")
        c1, c2 = st.columns(2)
        p = c1.selectbox("Projeto", lista_projs)
        t = c2.selectbox("Tipo", ["Front-end", "Back-end", "Infra", "Reunião", "Outros"])
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
            # Concatena e salva usando a função blindada
            df_atualizado = pd.concat([df_lan, pd.DataFrame([novo])], ignore_index=True)
            salvar_master(df_atualizado)

with t_dash:
    meus = df_lan[df_lan["colaborador_email"] == user].copy()
    st.dataframe(meus.sort_values("data_registro", ascending=False), use_container_width=True, hide_index=True)

with t_admin:
    if user in ADMINS:
        st.markdown("### 🛡️ Painel do Administrador")
        # O Editor de Dados agora está dentro de um formulário para evitar envios acidentais/incompletos
        with st.form("form_admin"):
            st.info("Altere os dados abaixo e clique em 'Salvar Alterações'.")
            df_editado = st.data_editor(df_lan, num_rows="dynamic", use_container_width=True)
            
            if st.form_submit_button("💾 SALVAR ALTERAÇÕES NA PLANILHA"):
                salvar_master(df_editado)

with t_bi:
    if user in ADMINS:
        df_bi = df_lan.copy()
        df_bi["horas"] = pd.to_numeric(df_bi["horas"], errors="coerce").fillna(0)
        st.bar_chart(df_bi.groupby("projeto")["horas"].sum())

# --- BOTÃO DE EMERGÊNCIA NA SIDEBAR ---
st.sidebar.divider()
if st.sidebar.button("🆘 REPARAR PLANILHA"):
    df_reset = pd.DataFrame(columns=COLS_OFICIAIS)
    salvar_master(df_reset)