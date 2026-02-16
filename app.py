import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid

st.set_page_config(page_title="Gestão OnCall", layout="wide", page_icon="💸")

# --- 1. CONEXÃO ESTÁVEL (NÃO MEXA) ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"Erro de Conexão: {e}")
    st.stop()

# --- 2. CARREGAMENTO E TRATAMENTO DE DADOS ---
try:
    df_config = conn.read(worksheet="config", ttl=0)
    df_lancamentos = conn.read(worksheet="lancamentos", ttl=0)
except:
    df_config = pd.DataFrame(columns=["projetos", "emails_autorizados", "valor_hora"])
    df_lancamentos = pd.DataFrame(columns=["id", "data_registro", "competencia", "colaborador_email", "projeto", "horas", "descricao", "status_aprovaca", "data_decisao"])

# [TRATAMENTO] Garante que a coluna 'competencia' exista nos dados antigos
if "competencia" not in df_lancamentos.columns:
    if not df_lancamentos.empty and "data_registro" in df_lancamentos.columns:
        # Cria a competência baseada na data de registro antiga
        df_lancamentos["competencia"] = pd.to_datetime(df_lancamentos["data_registro"]).dt.strftime("%Y-%m")
    else:
        df_lancamentos["competencia"] = ""

# --- 3. VARIÁVEIS GLOBAIS ---
try:
    user_email = st.user.email
    if user_email is None: raise Exception()
except:
    user_email = "pedroivofernandesreis@gmail.com"

ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

# Listas
lista_projetos = df_config["projetos"].dropna().unique().tolist()
if not lista_projetos: lista_projetos = ["Sistema de horas"]

try:
    valor_hora_padrao = float(df_config["valor_hora"].dropna().iloc[0])
except:
    valor_hora_padrao = 100.0

# --- 4. SEGURANÇA ---
if user_email not in ADMINS and user_email not in df_config["emails_autorizados"].values:
    st.error(f"🔒 Acesso negado para {user_email}.")
    st.stop()

# --- 5. INTERFACE ---
st.title("🚀 Gestão OnCall")

tabs_list = ["📝 Lançar"]
if user_email in ADMINS:
    tabs_list += ["🛡️ Painel da Clau", "📊 BI & Financeiro", "⚙️ Config"]

abas = st.tabs(tabs_list)

# === ABA 1: LANÇAR ===
with abas[0]:
    st.caption(f"Logado como: {user_email}")
    with st.form("form_lan", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        proj = c1.selectbox("Projeto", lista_projetos)
        hor = c2.number_input("Horas", min_value=0.5, step=0.5, format="%.1f")
        
        # Competência automática (Mês Atual)
        comp_atual = datetime.now().strftime("%Y-%m")
        c3.text_input("Competência", value=comp_atual, disabled=True, help="O Admin pode alterar isso depois.")
        
        desc = st.text_area("Descrição da atividade")
        
        if st.form_submit_button("Enviar Registro"):
            novo = pd.DataFrame([{
                "id": str(uuid.uuid4()),
                "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "competencia": comp_atual, # Salva o mês atual
                "colaborador_email": user_email,
                "projeto": proj,
                "horas": hor,
                "descricao": desc,
                "status_aprovaca": "Pendente",
                "data_decisao": ""
            }])
            final = pd.concat([df_lancamentos, novo], ignore_index=True).astype(str)
            conn.update(worksheet="lancamentos", data=final)
            st.success("Sucesso! Registro enviado.")
            st.rerun()

# === ÁREA ADMIN ===
if user_email in ADMINS:
    
    # ABA 2: PAINEL DA CLAU (EDIÇÃO TOTAL)
    with abas[1]:
        st.subheader("🛡️ Central de Controle")
        st.info("Aqui você pode aprovar e **corrigir a competência** ou horas de qualquer lançamento.")
        
        # Editor poderoso: Permite mudar competência, horas, projeto e status
        edited_df = st.data_editor(
            df_lancamentos,
            column_config={
                "status_aprovaca": st.column_config.SelectboxColumn("Status", options=["Pendente", "Aprovado", "Rejeitado"], required=True),
                "competencia": st.column_config.TextColumn("Competência (AAAA-MM)", help="Edite para mudar o mês de pagamento"),
                "horas": st.column_config.NumberColumn("Horas", min_value=0, step=0.5),
                "projeto": st.column_config.SelectboxColumn("Projeto", options=lista_projetos),
                "data_registro": st.column_config.TextColumn("Data Real", disabled=True)
            },
            disabled=["id", "colaborador_email"], 
            hide_index=True,
            num_rows="dynamic",
            key="editor_clau"
        )
        
        if st.button("💾 Salvar Alterações"):
            # Atualiza data de decisão se aprovado
            for i, row in edited_df.iterrows():
                if row["status_aprovaca"] != "Pendente" and (pd.isna(row["data_decisao"]) or row["data_decisao"] == ""):
                    edited_df.at[i, "data_decisao"] = datetime.now().strftime("%Y-%m-%d")
            
            conn.update(worksheet="lancamentos", data=edited_df.astype(str))
            st.success("Base de dados atualizada!")
            st.rerun()

    # ABA 3: BI & FINANCEIRO
    with abas[2]:
        st.subheader("📊 Inteligência Financeira")
        
        # Prepara dados (converte texto para número)
        df_bi = df_lancamentos.copy()
        df_bi["horas"] = pd.to_numeric(df_bi["horas"], errors="coerce").fillna(0)
        
        # --- FILTRO DE COMPETÊNCIA ---
        col_filtro, col_kpi = st.columns([1, 3])
        
        with col_filtro:
            # Lista de meses existentes nos dados
            meses_disponiveis = sorted(df_bi["competencia"].unique().tolist(), reverse=True)
            if not meses_disponiveis: meses_disponiveis = [datetime.now().strftime("%Y-%m")]
            
            mes_selecionado = st.selectbox("📅 Filtrar Competência", ["TODOS"] + meses_disponiveis)
        
        # Aplica o filtro
        if mes_selecionado != "TODOS":
            df_view = df_bi[df_bi["competencia"] == mes_selecionado]
        else:
            df_view = df_bi
            
        # Filtra só aprovados para conta financeira
        aprovados = df_view[df_view["status_aprovaca"] == "Aprovado"]
        
        # --- KPIs ---
        total_h = aprovados["horas"].sum()
        total_custo = total_h * valor_hora_padrao
        
        with col_kpi:
            k1, k2, k3 = st.columns(3)
            k1.metric("Horas Aprovadas", f"{total_h:.1f}h")
            k2.metric("Custo Total", f"R$ {total_custo:,.2f}")
            k3.metric("Lançamentos", len(aprovados))
        
        st.divider()
        
        # --- TABELA DE COLABORADORES (O PEDIDO) ---
        c_bi1, c_bi2 = st.columns(2)
        
        with c_bi1:
            st.markdown("### 👥 Pagamentos por Colaborador")
            if not aprovados.empty:
                fechamento = aprovados.groupby("colaborador_email").agg(
                    Horas=("horas", "sum")
                ).reset_index()
                
                fechamento["A Pagar (R$)"] = fechamento["Horas"] * valor_hora_padrao
                
                st.dataframe(
                    fechamento,
                    column_config={
                        "A Pagar (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
                        "Horas": st.column_config.NumberColumn(format="%.1f h")
                    },
                    hide_index=True,
                    use_container_width=True
                )
            else:
                st.info("Sem dados aprovados no período.")
        
        with c_bi2:
            st.markdown("### 🏗️ Custo por Projeto (CAC)")
            if not aprovados.empty:
                # Custo = Horas * Valor Hora
                custo_proj = aprovados.groupby("projeto")["horas"].sum() * valor_hora_padrao
                st.bar_chart(custo_proj)
                st.caption("Eixo Y: Custo em Reais (R$)")

    # ABA 4: CONFIGURAÇÕES
    with abas[3]:
        st.subheader("Configurações")
        st.warning("⚠️ Cuidado: Se apagar linhas aqui, elas somem do Google Sheets.")
        
        conf_edit = st.data_editor(df_config, num_rows="dynamic")
        
        if st.button("Salvar Configurações"):
            conn.update(worksheet="config", data=conf_edit.astype(str))
            st.success("Configuração salva com sucesso!")