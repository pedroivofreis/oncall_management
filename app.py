import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid
import time

st.set_page_config(page_title="Oncall Management - v6.9.2", layout="wide", page_icon="🚀")

# --- CONEXÃO ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- CARREGAMENTO ---
df_config = conn.read(worksheet="config", ttl=0)
df_lancamentos = conn.read(worksheet="lancamentos", ttl=0)
# Normaliza para evitar erros de case-sensitive
df_lancamentos.columns = [c.strip().lower() for c in df_lancamentos.columns]

# --- CONFIGS ---
df_u = df_config[["emails_autorizados", "valor_hora"]].copy()
df_u["valor_hora"] = pd.to_numeric(df_u["valor_hora"], errors="coerce").fillna(0.0)
dict_valores = dict(zip(df_u["emails_autorizados"].str.strip(), df_u["valor_hora"]))
lista_projetos = df_config["projetos"].dropna().unique().tolist()
ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

# --- LOGIN ---
st.sidebar.title("🔐 Acesso")
user_email = st.sidebar.selectbox("Identifique-se:", options=["Selecione..."] + sorted(list(dict_valores.keys())))
autenticado = False

if user_email != "Selecione...":
    if user_email in ADMINS:
        senha = st.sidebar.text_input("Senha Admin", type="password")
        if senha == "Humana1002*": autenticado = True
    else: autenticado = True

if not autenticado:
    st.info("👈 Identifique-se na barra lateral.")
    st.stop()

# --- TABS ---
abas_list = ["📝 Lançar", "🛡️ Painel da Clau", "📊 BI & Financeiro"]
abas = st.tabs(abas_list) if user_email in ADMINS else st.tabs(["📝 Lançar"])

# === ABA 1: LANÇAR ===
with abas[0]:
    with st.form("form_lan", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        proj = c1.selectbox("Projeto", lista_projetos)
        tipo = c2.selectbox("Tipo", ["Desenvolvimento", "Reunião", "Infra", "Outros"])
        data_f = c3.date_input("Data", value=datetime.now())
        hrs = st.number_input("Horas", min_value=0.5, step=0.5)
        desc = st.text_area("Descrição")
        
        if st.form_submit_button("Enviar Lançamento"):
            # ORDEM DAS COLUNAS PARA O APPS SCRIPT: A(id), B(data), C(email), D(proj), E(horas), F(status)... J(desc)
            novo = {
                "id": str(uuid.uuid4()),
                "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "colaborador_email": user_email,
                "projeto": proj,
                "horas": str(hrs),
                "status_aprovaca": "Pendente", # COLUNA F (6)
                "data_decisao": "",
                "competencia": data_f.strftime("%Y-%m"),
                "tipo": tipo,
                "descricão": desc # COLUNA J (10)
            }
            df_final = pd.concat([df_lancamentos, pd.DataFrame([novo])], ignore_index=True)
            conn.update(worksheet="lancamentos", data=df_final.astype(str))
            st.success("✅ Enviado! E-mail de notificação disparado.")
            time.sleep(1); st.rerun()

# === ABA BI (SOMENTE ADMIN) ===
if user_email in ADMINS:
    with abas[2]:
        st.subheader("📊 Inteligência Financeira")
        df_bi = df_lancamentos.copy()
        df_bi["horas"] = pd.to_numeric(df_bi["horas"], errors="coerce").fillna(0)
        df_bi["custo"] = df_bi["horas"] * df_bi["colaborador_email"].str.strip().map(dict_valores).fillna(0)
        
        apr = df_bi[df_bi["status_aprovaca"].str.contains("Aprovado", case=False, na=False)]
        
        k1, k2 = st.columns(2)
        k1.metric("Total Horas", f"{apr['horas'].sum():.1f}h")
        k2.metric("Total Gasto", f"R$ {apr['custo'].sum():,.2f}")
        
        st.divider()
        st.markdown("### 👥 Pagamentos Detalhados")
        if not apr.empty:
            pags = apr.groupby("colaborador_email").agg(Horas=("horas", "sum"), Receber=("custo", "sum")).reset_index()
            st.dataframe(pags, column_config={"Receber": st.column_config.NumberColumn(format="R$ %.2f")}, use_container_width=True)