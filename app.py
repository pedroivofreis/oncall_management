import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid
import time

# Configuração da Página
st.set_page_config(page_title="Oncall Management - v13.1 Full Safe", layout="wide", page_icon="🛡️")

# --- 1. CONEXÃO ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 2. LEITURA PASSIVA COM TRAVA DE SEGURANÇA ---
try:
    # Limpa cache para garantir leitura real do Google
    conn.clear()
    
    # Tenta ler as abas
    try:
        df_lan = conn.read(worksheet="lancamentos", ttl=0)
        df_u_raw = conn.read(worksheet="config_usuarios", ttl=0)
        df_p_raw = conn.read(worksheet="config_projetos", ttl=0)
    except Exception as e:
        st.error(f"⚠️ O Google bloqueou temporariamente por excesso de acessos (Erro 429). Aguarde 2 minutos e dê F5. Detalhe: {e}")
        st.stop()

    # === VERIFICAÇÃO RIGOROSA (O ESCUDO) ===
    # Normaliza as colunas lidas para minúsculo para comparar
    cols_lidas = [str(c).strip().lower() for c in df_lan.columns]
    
    # Colunas que PRECISAM existir para o sistema funcionar
    cols_obrigatorias = ["projeto", "horas", "colaborador_email", "status_aprovaca"]
    
    # Se faltar alguma, o app TRAVA AQUI e protege sua planilha.
    if not set(cols_obrigatorias).issubset(cols_lidas):
        st.error("🚨 ERRO DE ESTRUTURA DETECTADO - MODO DE PROTEÇÃO ATIVADO")
        st.markdown(f"""
        **O sistema leu a planilha e percebeu que os cabeçalhos sumiram.**
        Para evitar que seus dados sejam apagados, o sistema bloqueou qualquer gravação.
        
        **Ação Necessária:**
        1. Vá na planilha do Google agora.
        2. Restaure a Linha 1 com: `id, data_registro, colaborador_email, projeto, horas, status_aprovaca...`
        3. Volte aqui e atualize a página.
        """)
        st.stop() # <--- FIM DA LINHA. NADA É SALVO SE TIVER ERRO.

    # Se passou, normaliza o DF
    df_lan.columns = cols_lidas
    for col in ['email_enviado', 'valor_hora_historico']:
        if col not in df_lan.columns: df_lan[col] = ""

except Exception as e:
    st.error(f"Erro Crítico no carregamento: {e}")
    st.stop()

# --- 3. PROCESSAMENTO DE DADOS ---
lista_projetos = df_p_raw["projetos"].dropna().astype(str).str.strip().unique().tolist()
dict_users = {}
for _, row in df_u_raw.dropna(subset=["emails_autorizados"]).iterrows():
    dict_users[row["emails_autorizados"].strip()] = {
        "valor": pd.to_numeric(row["valor_hora"], errors='coerce') or 0,
        "senha": str(row["senhas"]).strip()
    }
ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

# --- 4. FUNÇÃO SALVAR BLINDADA ---
def salvar(aba, df):
    try:
        conn.clear()
        # fillna("") e astype(str) são vitais para o Google Sheets aceitar
        conn.update(worksheet=aba, data=df.fillna("").astype(str))
        st.success(f"✅ Dados gravados com sucesso na aba '{aba}'!")
        time.sleep(1); st.rerun()
    except Exception as e:
        st.error(f"❌ Erro de Gravação: {e}")

# --- 5. LOGIN ---
st.sidebar.title("🛡️ OnCall System")
user_email = st.sidebar.selectbox("Usuário:", options=["Selecione..."] + sorted(list(dict_users.keys())))
autenticado = False

if user_email != "Selecione..." and dict_users:
    senha = st.sidebar.text_input("Senha:", type="password")
    if senha == dict_users.get(user_email, {}).get("senha"): autenticado = True
    elif senha: st.sidebar.error("Senha incorreta.")

if not autenticado:
    st.info("👈 Identifique-se para acessar.")
    st.stop()

# --- 6. INTERFACE COMPLETA ---
tabs_list = ["📝 Lançar Horas", "📊 Meu Dashboard"]
if user_email in ADMINS:
    tabs_list += ["🛡️ Gerencial", "📈 BI Financeiro", "⚙️ Configurações"]
tabs = st.tabs(tabs_list)

# === ABA 1: LANÇAR HORAS ===
with tabs[0]:
    metodo = st.radio("Método de Lançamento:", ["Dinâmico (+)", "Importação em Massa (Excel)"], horizontal=True)
    
    if metodo == "Dinâmico (+)":
        with st.form("form_lancamento"):
            st.markdown("### ⏱️ Registrar Atividades")
            df_template = pd.DataFrame(columns=["projeto", "tipo", "data", "horas", "descricão"])
            df_ed = st.data_editor(df_template, num_rows="dynamic", use_container_width=True,
                column_config={
                    "projeto": st.column_config.SelectboxColumn("Projeto", options=lista_projetos, required=True),
                    "tipo": st.column_config.SelectboxColumn("Tipo", options=["Front-end", "Back-end", "Banco de Dados", "Infra", "Testes", "Reunião", "Outros"], required=True),
                    "data": st.column_config.DateColumn("Data", default=datetime.now()),
                    "horas": st.column_config.NumberColumn("Horas", min_value=0.5, step=0.5),
                    "descricão": st.column_config.TextColumn("Descrição Detalhada")
                })
            
            if st.form_submit_button("🚀 Gravar Lançamentos"):
                if not df_ed.empty:
                    novos = []
                    v_h = dict_users[user_email]["valor"]
                    for _, r in df_ed.iterrows():
                        if pd.isna(r["projeto"]): continue
                        novos.append({
                            "id": str(uuid.uuid4()), "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "colaborador_email": user_email, "projeto": r["projeto"], "horas": str(r["horas"]),
                            "status_aprovaca": "Pendente", "data_decisao": "", 
                            "competencia": r["data"].strftime("%Y-%m")[:7],
                            "tipo": r["tipo"], "descricão": r["descricão"], 
                            "email_enviado": "", "valor_hora_historico": str(v_h)
                        })
                    if novos:
                        # Concatena mantendo o histórico
                        salvar("lancamentos", pd.concat([df_lan, pd.DataFrame(novos)], ignore_index=True))
    else:
        st.info("O arquivo deve conter: projeto, horas, tipo, descricão, data (YYYY-MM-DD)")
        arq = st.file_uploader("Subir Arquivo .xlsx ou .csv", type=["csv", "xlsx"])
        if arq and st.button("Confirmar Importação"):
            df_m = pd.read_csv(arq) if arq.name.endswith('.csv') else pd.read_excel(arq)
            v_h = dict_users[user_email]["valor"]
            novos_m = [{"id": str(uuid.uuid4()), "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "colaborador_email": user_email, "projeto": r["projeto"], "horas": str(r["horas"]), "status_aprovaca": "Pendente", "data_decisao": "", "competencia": str(r["data"])[:7], "tipo": r["tipo"], "descricão": r["descricão"], "email_enviado": "", "valor_hora_historico": str(v_h)} for _, r in df_m.iterrows()]
            salvar("lancamentos", pd.concat([df_lan, pd.DataFrame(novos_m)], ignore_index=True))

# === ABA 2: MEU DASHBOARD ===
with tabs[1]:
    meus_dados = df_lan[df_lan["colaborador_email"] == user_email].copy()
    meus_dados["horas"] = pd.to_numeric(meus_dados["horas"], errors="coerce").fillna(0)
    
    st.subheader(f"Visão Geral: {user_email}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("✅ Aprovadas", f"{meus_dados[meus_dados['status_aprovaca'] == 'Aprovado']['horas'].sum():.1f}h")
    c2.metric("💰 Pagas", f"{meus_dados[meus_dados['status_aprovaca'] == 'Pago']['horas'].sum():.1f}h")
    c3.metric("⏳ Pendentes", f"{meus_dados[meus_dados['status_aprovaca'] == 'Pendente']['horas'].sum():.1f}h")
    c4.metric("🚫 Rejeitadas", f"{meus_dados[meus_dados['status_aprovaca'] == 'Rejeitado']['horas'].sum():.1f}h")
    
    st.divider()
    st.dataframe(meus_dados.sort_values("data_registro", ascending=False), use_container_width=True, hide_index=True)

# === ABA 3: GERENCIAL (ADMIN) ===
if user_email in ADMINS:
    with tabs[2]:
        sub1, sub2 = st.tabs(["📋 Listagem Geral & Status", "💰 Controle de Pagamentos"])
        with sub1:
            with st.form("form_admin_geral"):
                st.markdown("### Edição Master")
                df_editor_admin = st.data_editor(df_lan, num_rows="dynamic", use_container_width=True)
                if st.form_submit_button("💾 Salvar Alterações na Master"):
                    salvar("lancamentos", df_editor_admin)
        with sub2:
            st.markdown("### Fechamento de Mês")
            mes_sel = st.selectbox("Selecione a Competência:", sorted(df_lan["competencia"].unique(), reverse=True))
            
            # Filtra Aprovados da competência
            df_pag = df_lan[(df_lan["competencia"] == mes_sel) & (df_lan["status_aprovaca"] == "Aprovado")].copy()
            df_pag["horas"] = pd.to_numeric(df_pag["horas"], errors="coerce").fillna(0)
            
            # Lógica Financeira: Usa valor histórico se existir, senão usa o atual
            df_pag["v_h"] = pd.to_numeric(df_pag["valor_hora_historico"], errors="coerce").fillna(
                df_pag["colaborador_email"].map(lambda x: dict_users.get(x, {}).get("valor", 0))
            )
            df_pag["total"] = df_pag["v_h"] * df_pag["horas"]
            
            st.dataframe(df_pag.groupby("colaborador_email")["total"].sum().reset_index().style.format({"total": "R$ {:.2f}"}), use_container_width=True)
            
            if st.button(f"💸 Confirmar Pagamento Total de {mes_sel}"):
                df_lan.loc[(df_lan["competencia"] == mes_sel) & (df_lan["status_aprovaca"] == "Aprovado"), "status_aprovaca"] = "Pago"
                salvar("lancamentos", df_lan)

    # === ABA 4: BI FINANCEIRO ===
    with tabs[3]:
        st.subheader("📊 Inteligência de Negócio")
        filt_meses = st.multiselect("Filtrar Período:", sorted(df_lan["competencia"].unique()), default=sorted(df_lan["competencia"].unique()))
        
        df_bi = df_lan[df_lan["competencia"].isin(filt_meses)].copy()
        df_bi["horas"] = pd.to_numeric(df_bi["horas"], errors="coerce").fillna(0)
        df_bi["v_h"] = pd.to_numeric(df_bi["valor_hora_historico"], errors="coerce").fillna(
            df_bi["colaborador_email"].map(lambda x: dict_users.get(x, {}).get("valor", 0))
        )
        df_bi["custo"] = df_bi["horas"] * df_bi["v_h"]
        
        # Só considera o que gera custo real (Aprovado ou Pago)
        validos = df_bi[df_bi["status_aprovaca"].isin(["Aprovado", "Pago"])]
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Investimento Total", f"R$ {validos['custo'].sum():,.2f}")
        m2.metric("Horas Totais", f"{validos['horas'].sum():.1f}h")
        ticket = (validos['custo'].sum() / validos['horas'].sum()) if validos['horas'].sum() > 0 else 0
        m3.metric("Ticket Médio/h", f"R$ {ticket:,.2f}")
        
        st.divider()
        g1, g2 = st.columns(2)
        with g1:
            st.markdown("##### Custo por Projeto")
            st.bar_chart(validos.groupby("projeto")["custo"].sum(), color="#2e7d32")
        with g2:
            st.markdown("##### Horas por Tipo")
            st.bar_chart(validos.groupby("tipo")["horas"].sum(), color="#29b5e8")

    # === ABA 5: CONFIGURAÇÕES ===
    with tabs[4]:
        st.info("⚠️ Cuidado: Alterações aqui impactam todo o sistema.")
        t_user, t_proj = st.tabs(["👥 Usuários & Permissões", "🏗️ Projetos Ativos"])
        
        with t_user:
            with st.form("form_users"):
                ed_users = st.data_editor(df_u_raw, num_rows="dynamic", use_container_width=True)
                if st.form_submit_button("💾 Salvar Usuários"):
                    salvar("config_usuarios", ed_users.dropna(subset=["emails_autorizados"]))
                    
        with t_proj:
            with st.form("form_projs"):
                ed_projs = st.data_editor(df_p_raw, num_rows="dynamic", use_container_width=True)
                if st.form_submit_button("💾 Salvar Projetos"):
                    salvar("config_projetos", ed_projs.dropna(subset=["projetos"]))

# --- RODAPÉ ---
st.markdown("---")
st.markdown(f"<p style='text-align: center; color: grey;'>OnCall Management System v13.1 | <b>Pedro Reis</b></p>", unsafe_allow_html=True)