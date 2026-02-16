import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid
import time

st.set_page_config(page_title="Oncall Management - v6.9 (by Pedro Reis)", layout="wide", page_icon="🚀")

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
    
    # Padronização de nomes de colunas para o BI funcionar independente da planilha
    # Isso evita que o erro de 'coluna não encontrada' suma com a tabela
    df_lancamentos.columns = [c.strip().lower() for c in df_lancamentos.columns]
except Exception as e:
    st.error(f"Erro ao carregar dados: {e}")
    st.stop()

# --- 3. CONFIGURAÇÕES & USUÁRIOS ---
try:
    # Projetos
    raw_p = df_config["projetos"].dropna().unique().tolist()
    lista_projetos = [str(x).strip() for x in raw_p if str(x).strip() not in ["", "nan", "None"]]
    
    # Valores Hora (Dicionário para o cálculo do BI)
    df_u = df_config[["emails_autorizados", "valor_hora"]].copy()
    df_u["valor_hora"] = pd.to_numeric(df_u["valor_hora"], errors="coerce").fillna(0.0)
    dict_valores = dict(zip(df_u["emails_autorizados"].str.strip(), df_u["valor_hora"]))

    ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]
except:
    st.error("Erro nas configurações. Verifique a aba 'config' no Sheets.")
    st.stop()

# --- 4. LOGIN (Senha: Humana1002*) ---
st.sidebar.title("🔐 Acesso")
email_detectado = None
try:
    if hasattr(st, "context"): email_detectado = st.context.user.email
    elif hasattr(st, "user"): email_detectado = st.user.get("email")
except: email_detectado = None

user_email = None
autenticado = False

if email_detectado:
    user_email = email_detectado
    autenticado = True
else:
    user_email = st.sidebar.selectbox("Identifique-se:", options=["Selecione..."] + sorted(list(dict_valores.keys())))
    if user_email != "Selecione...":
        if user_email in ADMINS:
            senha = st.sidebar.text_input("Senha Admin", type="password")
            if senha == "Humana1002*": autenticado = True
            elif senha: st.sidebar.error("Senha incorreta!")
        else: autenticado = True

if not autenticado:
    st.info("👈 Identifique-se na lateral.")
    st.stop()

# --- 5. INTERFACE ---
st.title("Oncall Management - v6.9")
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
            # MONTANDO O DICIONÁRIO NA ORDEM EXATA DA SUA PLANILHA (A até J)
            # A=id, B=data_registro, C=email, D=projeto, E=horas, F=desc, G=status, H=decisao, I=comp, J=tipo
            novo_dado = {
                "id": str(uuid.uuid4()),
                "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "colaborador_email": user_email,
                "projeto": proj,
                "horas": str(hrs),
                "descricão": desc, # Coluna F
                "status_aprovaca": "Pendente", # Coluna G -> Grita para o Apps Script enviar e-mail!
                "data_decisao": "",
                "competencia": data_f.strftime("%Y-%m"),
                "tipo": tipo
            }
            
            # Converte para DataFrame mantendo a ordem das colunas da planilha
            novo_df = pd.DataFrame([novo_dado])
            df_final = pd.concat([df_lancamentos, novo_df], ignore_index=True)
            
            conn.update(worksheet="lancamentos", data=df_final.astype(str))
            st.success("Lançamento enviado! A Clau foi notificada por e-mail. 📧")
            time.sleep(1)
            st.rerun()

# === ÁREA ADMIN ===
if user_email in ADMINS:
    # PAINEL DE APROVAÇÃO
    with abas[1]:
        st.subheader("🛡️ Central de Decisões")
        df_edit = st.data_editor(
            df_lancamentos,
            column_config={
                "status_aprovaca": st.column_config.SelectboxColumn("Status", options=["Pendente", "Aprovado", "Rejeitado"]),
                "tipo": st.column_config.SelectboxColumn("Tipo", options=["Front-end", "Back-end", "Banco de Dados", "Infraestrutura", "Testes", "Reunião", "Outros"]),
            },
            disabled=["id", "colaborador_email", "data_registro"], hide_index=True
        )
        if st.button("Salvar Alterações"):
            for i, row in df_edit.iterrows():
                if row["status_aprovaca"] != "Pendente" and not row["data_decisao"]:
                    df_edit.at[i, "data_decisao"] = datetime.now().strftime("%Y-%m-%d")
            conn.update(worksheet="lancamentos", data=df_edit.astype(str))
            st.success("Planilha Atualizada!"); st.rerun()

    # BI & FINANCEIRO (RESTAURADO)
    with abas[2]:
        st.subheader("📊 BI & Financeiro")
        df_bi = df_lancamentos.copy()
        df_bi["horas"] = pd.to_numeric(df_bi["horas"], errors="coerce").fillna(0)
        df_bi["custo"] = df_bi["horas"] * df_bi["colaborador_email"].str.strip().map(dict_valores).fillna(0)
        
        apr = df_bi[df_bi["status_aprovaca"] == "Aprovado"]
        
        k1, k2, k3 = st.columns(3)
        k1.metric("Horas Aprovadas", f"{apr['horas'].sum():.1f}h")
        k2.metric("Custo Total", f"R$ {apr['custo'].sum():,.2f}")
        k3.metric("Registros", len(apr))
        
        st.divider()
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### 🏗️ Custo por Projeto")
            st.bar_chart(apr.groupby("projeto")["custo"].sum(), color="#2e7d32")
        with c2:
            st.markdown("### 🛠️ Horas por Tipo")
            st.bar_chart(apr.groupby("tipo")["horas"].sum(), color="#29b5e8")
            
        st.divider()
        st.markdown("### 👥 Tabela de Pagamentos")
        if not apr.empty:
            pags = apr.groupby("colaborador_email").agg(Total_Horas=("horas", "sum"), A_Receber=("custo", "sum")).reset_index()
            st.dataframe(pags, column_config={"A_Receber": st.column_config.NumberColumn(format="R$ %.2f")}, hide_index=True, use_container_width=True)

    # CONFIGURAÇÕES
    with abas[3]:
        st.subheader("⚙️ Configurações")
        st.data_editor(df_config, num_rows="dynamic", key="c_edit")
        if st.button("Salvar Configs"):
            conn.update(worksheet="config", data=st.session_state.c_edit.astype(str))
            st.success("Salvo!"); st.rerun()