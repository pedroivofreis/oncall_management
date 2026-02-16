import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid

st.set_page_config(page_title="Gestão OnCall", layout="wide", page_icon="💸")

# --- 1. CONEXÃO BLINDADA (NÃO MEXER) ---
try:
    if "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
        creds = dict(st.secrets["connections"]["gsheets"])
        creds["private_key"] = creds["private_key"].replace("\\n", "\n")
    else:
        creds = {}
except Exception:
    creds = {}

try:
    if creds:
        conn = st.connection("gsheets", type=GSheetsConnection, **creds)
    else:
        conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error("Erro Fatal de Conexão.")
    st.stop()

# --- 2. CARREGAMENTO INTELIGENTE ---
try:
    df_config = conn.read(worksheet="config", ttl=0)
    df_lancamentos = conn.read(worksheet="lancamentos", ttl=0)
    
    # Tratamento de erro se a planilha estiver vazia
    if df_config.empty:
        df_config = pd.DataFrame(columns=["projetos", "emails_autorizados", "valor_hora"])
    if df_lancamentos.empty:
        df_lancamentos = pd.DataFrame(columns=["id", "data_registro", "colaborador_email", "projeto", "horas", "descricao", "status_aprovaca", "data_decisao"])
        
except Exception:
    st.warning("Criando estrutura inicial das planilhas...")
    df_config = pd.DataFrame(columns=["projetos", "emails_autorizados", "valor_hora"])
    df_lancamentos = pd.DataFrame(columns=["id", "data_registro", "colaborador_email", "projeto", "horas", "descricao", "status_aprovaca", "data_decisao"])

# --- 3. VARIÁVEIS GLOBAIS ---
try:
    user_email = st.user.email
except:
    user_email = "pedroivofernandesreis@gmail.com"

ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

# Pega lista de projetos e valor hora
lista_projetos = df_config["projetos"].dropna().unique().tolist()
if not lista_projetos: lista_projetos = ["Consultoria Geral", "Desenvolvimento", "Reunião"]

try:
    valor_hora_padrao = float(df_config["valor_hora"].dropna().iloc[0])
except:
    valor_hora_padrao = 100.0 # Valor default se não tiver na planilha

# --- 4. CONTROLE DE ACESSO ---
if user_email not in ADMINS and user_email not in df_config["emails_autorizados"].values:
    st.error(f"🔒 Acesso negado para {user_email}. Fale com a Clau.")
    st.stop()

# --- 5. INTERFACE ---
st.title(f"🚀 Gestão OnCall - Olá, {user_email.split('@')[0]}!")

tabs = ["📝 Lançar Horas"]
if user_email in ADMINS:
    tabs += ["🛡️ Painel da Clau", "📊 Dashboard BI", "⚙️ Configurações"]

abas = st.tabs(tabs)

# === ABA 1: LANÇAR HORAS ===
with abas[0]:
    st.markdown("### Novo Registro")
    with st.form("form_lan", clear_on_submit=True):
        col1, col2 = st.columns(2)
        proj = col1.selectbox("Projeto", lista_projetos)
        hor = col2.number_input("Horas Trabalhadas", min_value=0.5, step=0.5, format="%.1f")
        desc = st.text_area("O que você fez?")
        
        if st.form_submit_button("Enviar para Aprovação"):
            novo = pd.DataFrame([{
                "id": str(uuid.uuid4()),
                "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "colaborador_email": user_email,
                "projeto": proj,
                "horas": hor,
                "descricao": desc,
                "status_aprovaca": "Pendente",
                "data_decisao": ""
            }])
            df_final = pd.concat([df_lancamentos, novo], ignore_index=True).astype(str)
            conn.update(worksheet="lancamentos", data=df_final)
            st.success("Lançamento enviado! ✅")
            st.rerun()

# Só mostra o resto se for ADMIN
if user_email in ADMINS:
    
    # === ABA 2: PAINEL DA CLAU (APROVAÇÃO) ===
    with abas[1]:
        st.markdown("### 🛡️ Central de Aprovação")
        
        # Filtra pendentes
        pendentes = df_lancamentos[df_lancamentos["status_aprovaca"] == "Pendente"].copy()
        
        if pendentes.empty:
            st.info("Tudo limpo! Nenhuma hora pendente de aprovação.")
        else:
            st.write(f"Existem **{len(pendentes)}** lançamentos aguardando análise.")
            
            # Edição direta na tabela
            editor = st.data_editor(
                pendentes,
                column_config={
                    "status_aprovaca": st.column_config.SelectboxColumn(
                        "Ação",
                        options=["Pendente", "Aprovado", "Rejeitado"],
                        required=True
                    ),
                    "id": None, # Esconde o ID
                    "data_decisao": None
                },
                disabled=["data_registro", "colaborador_email", "projeto", "horas", "descricao"],
                hide_index=True,
                key="editor_aprovacao"
            )
            
            if st.button("💾 Salvar Alterações de Status"):
                # Atualiza o dataframe principal com as mudanças
                for index, row in editor.iterrows():
                    # Se o status mudou de Pendente para outra coisa
                    if row["status_aprovaca"] != "Pendente":
                        # Acha a linha no DF original pelo ID
                        idx_orig = df_lancamentos[df_lancamentos["id"] == row["id"]].index
                        if not idx_orig.empty:
                            df_lancamentos.at[idx_orig[0], "status_aprovaca"] = row["status_aprovaca"]
                            df_lancamentos.at[idx_orig[0], "data_decisao"] = datetime.now().strftime("%Y-%m-%d")
                
                conn.update(worksheet="lancamentos", data=df_lancamentos.astype(str))
                st.success("Status atualizados com sucesso!")
                st.rerun()

    # === ABA 3: DASHBOARD BI ===
    with abas[2]:
        st.markdown("### 📊 Performance Financeira")
        
        if df_lancamentos.empty:
            st.warning("Sem dados para exibir ainda.")
        else:
            # Tratamento de Tipos para Gráficos
            df_bi = df_lancamentos.copy()
            df_bi["horas"] = pd.to_numeric(df_bi["horas"], errors="coerce").fillna(0)
            df_bi["data_registro"] = pd.to_datetime(df_bi["data_registro"], errors="coerce")
            
            # Filtros
            aprovadas = df_bi[df_bi["status_aprovaca"] == "Aprovado"]
            total_horas = aprovadas["horas"].sum()
            faturamento = total_horas * valor_hora_padrao
            
            # KPI Cards
            k1, k2, k3 = st.columns(3)
            k1.metric("Horas Aprovadas", f"{total_horas:.1f} h")
            k2.metric("Faturamento Estimado", f"R$ {faturamento:,.2f}")
            k3.metric("Valor Hora Base", f"R$ {valor_hora_padrao}")
            
            st.divider()
            
            # Gráficos
            g1, g2 = st.columns(2)
            
            with g1:
                st.subheader("Horas por Projeto")
                horas_proj = aprovadas.groupby("projeto")["horas"].sum()
                st.bar_chart(horas_proj)
                
            with g2:
                st.subheader("Evolução Mensal")
                if not aprovadas.empty:
                    aprovadas["mes"] = aprovadas["data_registro"].dt.strftime("%Y-%m")
                    evolucao = aprovadas.groupby("mes")["horas"].sum()
                    st.line_chart(evolucao)
                else:
                    st.info("Aprovar horas para ver o gráfico.")

    # === ABA 4: CONFIGURAÇÕES ===
    with abas[3]:
        st.markdown("### ⚙️ Parâmetros do Sistema")
        
        st.info("Edite os projetos e o valor da hora aqui. As alterações vão direto para o Google Sheets.")
        
        config_editada = st.data_editor(df_config, num_rows="dynamic")
        
        if st.button("Atualizar Configurações"):
            conn.update(worksheet="config", data=config_editada.astype(str))
            st.success("Configurações salvas! Recarregue a página para aplicar.")