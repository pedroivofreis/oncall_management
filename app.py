import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid
import time

st.set_page_config(page_title="Oncall Management - v6.9.1 (by Pedro Reis)", layout="wide", page_icon="🚀")

# --- 1. CONEXÃO ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"Erro de Conexão: {e}")
    st.stop()

# --- 2. CARREGAMENTO ---
try:
    df_config = conn.read(worksheet="config", ttl=0)
    df_lancamentos = conn.read(worksheet="lancamentos", ttl=0)
    # Padroniza colunas para o BI não quebrar
    df_lancamentos.columns = [c.strip().lower() for c in df_lancamentos.columns]
except Exception as e:
    st.error("Erro ao carregar dados.")
    st.stop()

# --- 3. CONFIGURAÇÕES & VALORES ---
try:
    raw_p = df_config["projetos"].dropna().unique().tolist()
    lista_projetos = [str(x).strip() for x in raw_p if str(x).strip() not in ["", "nan", "None"]]
    
    df_u = df_config[["emails_autorizados", "valor_hora"]].copy()
    df_u["valor_hora"] = pd.to_numeric(df_u["valor_hora"], errors="coerce").fillna(0.0)
    dict_valores = dict(zip(df_u["emails_autorizados"].str.strip(), df_u["valor_hora"]))

    ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]
except:
    st.stop()

# --- 4. LOGIN (Senha: Humana1002*) ---
st.sidebar.title("🔐 Acesso")
user_email = st.sidebar.selectbox("Identifique-se:", options=["Selecione..."] + sorted(list(dict_valores.keys())))
autenticado = False

if user_email != "Selecione...":
    if user_email in ADMINS:
        senha = st.sidebar.text_input("Senha Admin", type="password")
        if senha == "Humana1002*": autenticado = True
    else: autenticado = True

if not autenticado:
    st.stop()

# --- 5. INTERFACE ---
abas_list = ["📝 Lançar", "🛡️ Painel da Clau", "📊 BI & Financeiro", "⚙️ Configurações"] if user_email in ADMINS else ["📝 Lançar"]
abas = st.tabs(abas_list)

# === ABA 1: LANÇAR ===
with abas[0]:
    with st.form("novo_lan", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        proj = c1.selectbox("Projeto", lista_projetos)
        tipo = c2.selectbox("Tipo", ["Front-end", "Back-end", "Banco de Dados", "Infraestrutura", "Testes", "Reunião", "Outros"])
        data_f = c3.date_input("Data da Atividade", value=datetime.now())
        
        c4, c5 = st.columns([1, 2])
        hrs = c4.number_input("Horas", min_value=0.5, step=0.5)
        desc = c5.text_area("Descrição")
        
        if st.form_submit_button("Enviar para Aprovação"):
            # Respeita a ordem exata da planilha (image_974b88)
            novo_dado = {
                "id": str(uuid.uuid4()),
                "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "colaborador_email": user_email,
                "projeto": proj,
                "horas": str(hrs),
                "descricão": desc,
                "status_aprovaca": "Pendente",
                "data_decisao": "",
                "competencia": data_f.strftime("%Y-%m"),
                "tipo": tipo
            }
            
            df_final = pd.concat([df_lancamentos, pd.DataFrame([novo_dado])], ignore_index=True)
            conn.update(worksheet="lancamentos", data=df_final.astype(str))
            st.success("Enviado! A Clau receberá um e-mail. 📧")
            time.sleep(1)
            st.rerun()

# === BI RESTAURADO (image_9753a2) ===
if user_email in ADMINS:
    with abas[2]:
        st.subheader("📊 BI & Financeiro")
        df_bi = df_lancamentos.copy()
        df_bi["horas"] = pd.to_numeric(df_bi["horas"], errors="coerce").fillna(0)
        df_bi["custo"] = df_bi["horas"] * df_bi["colaborador_email"].str.strip().map(dict_valores).fillna(0)
        
        apr = df_bi[df_bi["status_aprovaca"].str.contains("Aprovado", case=False, na=False)]
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### 🏗️ Custo por Projeto")
            st.bar_chart(apr.groupby("projeto")["custo"].sum(), color="#2e7d32")
        with c2:
            st.markdown("### 🛠️ Horas por Tipo")
            st.bar_chart(apr.groupby("tipo")["horas"].sum(), color="#29b5e8")
            
        st.markdown("### 👥 Tabela de Pagamentos")
        if not apr.empty:
            pags = apr.groupby("colaborador_email").agg(Horas=("horas", "sum"), Receber=("custo", "sum")).reset_index()
            st.dataframe(pags, column_config={"Receber": st.column_config.NumberColumn(format="R$ %.2f")}, hide_index=True, use_container_width=True)