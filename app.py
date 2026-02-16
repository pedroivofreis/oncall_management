import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid
import time

# Configuração da Página
st.set_page_config(page_title="Oncall Management - v7.1", layout="wide", page_icon="🚀")

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
    # Normaliza nomes de colunas para evitar conflitos no BI
    df_lancamentos.columns = [c.strip().lower() for c in df_lancamentos.columns]
except Exception as e:
    st.error("Erro ao carregar dados da planilha.")
    st.stop()

# --- 3. CONFIGURAÇÕES & USUÁRIOS ---
try:
    # Projetos dinâmicos da aba Config
    raw_p = df_config["projetos"].dropna().unique().tolist()
    lista_projetos = [str(x).strip() for x in raw_p if str(x).strip() not in ["", "nan", "None"]]
    if not lista_projetos: lista_projetos = ["Sistema de horas"]

    # Valores Hora por usuário
    df_u = df_config[["emails_autorizados", "valor_hora"]].copy()
    df_u["valor_hora"] = pd.to_numeric(df_u["valor_hora"], errors="coerce").fillna(0.0)
    dict_valores = dict(zip(df_u["emails_autorizados"].str.strip(), df_u["valor_hora"]))

    ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]
except Exception:
    st.stop()

# --- 4. LOGIN (Senha: Humana1002*) ---
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
    st.info("👈 Identifique-se na lateral para acessar o sistema.")
    st.stop()

# --- 5. INTERFACE (ABAS RESTAURADAS) ---
# Criando as 4 abas originais para Admins
if user_email in ADMINS:
    tabs = st.tabs(["📝 Lançar", "🛡️ Painel da Clau", "📊 BI & Financeiro", "⚙️ Configurações"])
else:
    tabs = st.tabs(["📝 Lançar"])

# === ABA 1: LANÇAR (TIPOS ORIGINAIS) ===
with tabs[0]:
    with st.form("novo_lan", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        proj = c1.selectbox("Projeto", lista_projetos)
        # Tipos restaurados conforme solicitado
        tipo = c2.selectbox("Tipo", ["Front-end", "Back-end", "Banco de Dados", "Infraestrutura", "Testes", "Reunião", "Outros"])
        data_f = c3.date_input("Data da Atividade", value=datetime.now())
        
        c4, c5 = st.columns([1, 2])
        hrs = c4.number_input("Horas", min_value=0.5, step=0.5)
        desc = c5.text_area("Descrição")
        
        if st.form_submit_button("Enviar para Aprovação"):
            # Ordem Exata para o Apps Script: A(id), B(data), C(email), D(proj), E(horas), F(status)... J(desc)
            novo = {
                "id": str(uuid.uuid4()),
                "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "colaborador_email": user_email,
                "projeto": proj,
                "horas": str(hrs),
                "status_aprovaca": "Pendente", # Coluna F (6) dispara o e-mail
                "data_decisao": "",
                "competencia": data_f.strftime("%Y-%m"),
                "tipo": tipo,
                "descricão": desc # Coluna J (10)
            }
            
            df_final = pd.concat([df_lancamentos, pd.DataFrame([novo])], ignore_index=True)
            conn.update(worksheet="lancamentos", data=df_final.astype(str))
            st.success("✅ Enviado! A Clau receberá a notificação por e-mail.")
            time.sleep(1)
            st.rerun()

# === ÁREA ADMIN (SOMENTE PEDRO E CLAU) ===
if user_email in ADMINS:
    
    # ABA 2: PAINEL DA CLAU (RESTAURADA)
    with tabs[1]:
        st.subheader("🛡️ Gestão de Aprovações")
        st.write("Edite diretamente na tabela para Aprovar ou Rejeitar registros.")
        
        df_edit = st.data_editor(
            df_lancamentos,
            column_config={
                "status_aprovaca": st.column_config.SelectboxColumn("Status", options=["Pendente", "Aprovado", "Rejeitado"]),
                "tipo": st.column_config.SelectboxColumn("Tipo", options=["Front-end", "Back-end", "Banco de Dados", "Infraestrutura", "Testes", "Reunião", "Outros"]),
            },
            disabled=["id", "colaborador_email", "data_registro"], hide_index=True
        )
        
        if st.button("💾 Salvar Decisões"):
            # Atualiza data de decisão nos registros que saíram de 'Pendente'
            for i, row in df_edit.iterrows():
                if row["status_aprovaca"] != "Pendente" and not row["data_decisao"]:
                    df_edit.at[i, "data_decisao"] = datetime.now().strftime("%Y-%m-%d")
            
            conn.update(worksheet="lancamentos", data=df_edit.astype(str))
            st.success("Planilha atualizada com sucesso!")
            st.rerun()

    # ABA 3: BI & FINANCEIRO
    with tabs[2]:
        st.subheader("📊 BI & Inteligência Financeira")
        df_bi = df_lancamentos.copy()
        df_bi["horas"] = pd.to_numeric(df_bi["horas"], errors="coerce").fillna(0)
        df_bi["custo"] = df_bi["horas"] * df_bi["colaborador_email"].str.strip().map(dict_valores).fillna(0)
        
        apr = df_bi[df_bi["status_aprovaca"].str.contains("Aprovado", case=False, na=False)]
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Horas Aprovadas", f"{apr['horas'].sum():.1f}h")
        c2.metric("Total a Pagar", f"R$ {apr['custo'].sum():,.2f}")
        c3.metric("Registros", len(apr))
        
        st.divider()
        g1, g2 = st.columns(2)
        with g1:
            st.markdown("### 🏗️ Custo por Projeto")
            st.bar_chart(apr.groupby("projeto")["custo"].sum(), color="#2e7d32")
        with g2:
            st.markdown("### 🛠️ Horas por Tipo")
            st.bar_chart(apr.groupby("tipo")["horas"].sum(), color="#29b5e8")
            
        st.divider()
        st.markdown("### 👥 Tabela de Pagamentos")
        if not apr.empty:
            pags = apr.groupby("colaborador_email").agg(Horas=("horas", "sum"), Receber=("custo", "sum")).reset_index()
            st.dataframe(pags, column_config={"Receber": st.column_config.NumberColumn(format="R$ %.2f")}, use_container_width=True, hide_index=True)

    # ABA 4: CONFIGURAÇÕES (RESTAURADA)
    with tabs[3]:
        st.subheader("⚙️ Configurações do Sistema")
        edit_config = st.data_editor(df_config, num_rows="dynamic", key="config_editor", hide_index=True)
        
        if st.button("💾 Salvar Configurações"):
            conn.update(worksheet="config", data=edit_config.astype(str))
            st.success("Novas configurações aplicadas!")
            time.sleep(1)
            st.rerun()