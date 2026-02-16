import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid
import time

# Configuração da Página
st.set_page_config(page_title="Oncall Management - v7.4", layout="wide", page_icon="🚀")

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
    
    # Limpeza básica: remove espaços dos nomes das colunas e coloca em minúsculo
    df_lancamentos.columns = [c.strip().lower() for c in df_lancamentos.columns]
    
    # GARANTIA: Se a coluna email_enviado não existir no arquivo, criamos ela no DataFrame
    if 'email_enviado' not in df_lancamentos.columns:
        df_lancamentos['email_enviado'] = ""
        
except Exception as e:
    st.error(f"Erro ao carregar dados: {e}")
    st.stop()

# --- 3. CONFIGURAÇÕES & USUÁRIOS ---
try:
    raw_p = df_config["projetos"].dropna().unique().tolist()
    lista_projetos = [str(x).strip() for x in raw_p if str(x).strip() not in ["", "nan", "None"]]
    
    df_u = df_config[["emails_autorizados", "valor_hora"]].copy()
    df_u["valor_hora"] = pd.to_numeric(df_u["valor_hora"], errors="coerce").fillna(0.0)
    dict_valores = dict(zip(df_u["emails_autorizados"].str.strip(), df_u["valor_hora"]))

    ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]
except Exception:
    st.stop()

# --- 4. LOGIN ---
st.sidebar.title("🔐 Acesso")
user_email = st.sidebar.selectbox("Identifique-se:", options=["Selecione..."] + sorted(list(dict_valores.keys())))
autenticado = False

if user_email != "Selecione...":
    if user_email in ADMINS:
        senha = st.sidebar.text_input("Senha Admin", type="password")
        if senha == "Humana1002*": autenticado = True
        elif senha: st.sidebar.error("Senha incorreta!")
    else:
        autenticado = True

if not autenticado:
    st.info("👈 Identifique-se na lateral.")
    st.stop()

# --- 5. INTERFACE ---
if user_email in ADMINS:
    tabs = st.tabs(["📝 Lançar", "🛡️ Painel da Clau", "📊 BI & Financeiro", "⚙️ Configurações"])
else:
    tabs = st.tabs(["📝 Lançar"])

# === ABA 1: LANÇAR ===
with tabs[0]:
    with st.form("novo_lan", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        proj = c1.selectbox("Projeto", lista_projetos)
        tipo = c2.selectbox("Tipo", ["Front-end", "Back-end", "Banco de Dados", "Infraestrutura", "Testes", "Reunião", "Outros"])
        data_f = c3.date_input("Data da Atividade", value=datetime.now())
        
        c4, c5 = st.columns([1, 2])
        hrs = c4.number_input("Horas", min_value=0.5, step=0.5)
        desc = c5.text_area("Descrição")
        
        if st.form_submit_button("Enviar para Aprovação"):
            novo = {
                "id": str(uuid.uuid4()),
                "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "colaborador_email": user_email,
                "projeto": proj,
                "horas": str(hrs),
                "status_aprovaca": "Pendente",
                "data_decisao": "",
                "competencia": data_f.strftime("%Y-%m"),
                "tipo": tipo,
                "descricão": desc,
                "email_enviado": "" # Deixa vazio para o robô do Google detectar
            }
            
            ordem_colunas = ["id", "data_registro", "colaborador_email", "projeto", "horas", 
                             "status_aprovaca", "data_decisao", "competencia", "tipo", "descricão", "email_enviado"]
            
            df_novo = pd.DataFrame([novo])[ordem_colunas]
            df_final = pd.concat([df_lancamentos, df_novo], ignore_index=True)
            
            conn.update(worksheet="lancamentos", data=df_final.astype(str))
            st.success("✅ Enviado! A notificação será processada em até 1 minuto.")
            time.sleep(1); st.rerun()

# === ÁREA ADMIN ===
if user_email in ADMINS:
    # ABA 2: PAINEL DA CLAU
    with tabs[1]:
        st.subheader("🛡️ Gestão de Aprovações")
        df_edit = st.data_editor(df_lancamentos, hide_index=True)
        if st.button("💾 Salvar Decisões"):
            conn.update(worksheet="lancamentos", data=df_edit.astype(str))
            st.success("Planilha atualizada!"); st.rerun()

    # ABA 3: BI & FINANCEIRO
    with tabs[2]:
        st.subheader("📊 BI & Inteligência Financeira")
        df_bi = df_lancamentos.copy()
        df_bi["horas"] = pd.to_numeric(df_bi["horas"], errors="coerce").fillna(0)
        df_bi["custo"] = df_bi["horas"] * df_bi["colaborador_email"].str.strip().map(dict_valores).fillna(0)
        
        # Filtro robusto para o BI não sumir
        apr = df_bi[df_bi["status_aprovaca"].str.strip().str.capitalize() == "Aprovado"]
        
        c1, c2 = st.columns(2)
        c1.metric("Horas Aprovadas", f"{apr['horas'].sum():.1f}h")
        c2.metric("Total a Pagar", f"R$ {apr['custo'].sum():,.2f}")
        
        st.divider()
        g1, g2 = st.columns(2)
        with g1:
            if not apr.empty:
                st.markdown("### 🏗️ Custo por Projeto")
                st.bar_chart(apr.groupby("projeto")["custo"].sum(), color="#2e7d32")
        with g2:
            if not apr.empty:
                st.markdown("### 🛠️ Horas por Tipo")
                st.bar_chart(apr.groupby("tipo")["horas"].sum(), color="#29b5e8")
            
        st.divider()
        st.markdown("### 👥 Tabela de Pagamentos")
        if not apr.empty:
            pags = apr.groupby("colaborador_email").agg(Horas=("horas", "sum"), Receber=("custo", "sum")).reset_index()
            st.dataframe(pags, column_config={"Receber": st.column_config.NumberColumn(format="R$ %.2f")}, use_container_width=True, hide_index=True)

    # ABA 4: CONFIGURAÇÕES
    with tabs[3]:
        st.subheader("⚙️ Configurações do Sistema")
        edit_config = st.data_editor(df_config, num_rows="dynamic", key="conf_edit", hide_index=True)
        if st.button("💾 Salvar Configurações"):
            conn.update(worksheet="config", data=edit_config.astype(str))
            st.success("Configurações salvas!"); st.rerun()