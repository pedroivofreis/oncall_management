import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid
import time

# Configuração da Página
st.set_page_config(page_title="Oncall Management - v11.0", layout="wide", page_icon="🚀")

# --- 1. CONEXÃO ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 2. CARREGAMENTO ---
try:
    # conn.clear() FORÇA o app a esquecer o cache antigo e ler o link novo dos secrets
    conn.clear()
    
    df_p_raw = conn.read(worksheet="config_projetos", ttl=0).dropna(how="all")
    df_u_raw = conn.read(worksheet="config_usuarios", ttl=0).dropna(how="all")
    df_lan = conn.read(worksheet="lancamentos", ttl=0).dropna(how="all")
    
    # Normalização
    df_lan.columns = [c.strip().lower() for c in df_lan.columns]
    
    # Colunas obrigatórias
    for col in ['email_enviado', 'valor_hora_historico']:
        if col not in df_lan.columns: df_lan[col] = ""
except Exception as e:
    st.error(f"Erro de Conexão: {e}. VERIFIQUE SE O LINK NO SECRETS.TOML ESTÁ ATUALIZADO!")
    st.stop()

# --- 3. CONFIGS ---
lista_projetos = df_p_raw["projetos"].dropna().astype(str).str.strip().unique().tolist()
dict_users = {}
for _, row in df_u_raw.dropna(subset=["emails_autorizados"]).iterrows():
    dict_users[row["emails_autorizados"].strip()] = {
        "valor": pd.to_numeric(row["valor_hora"], errors='coerce') or 0,
        "senha": str(row["senhas"]).strip()
    }
ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

# --- 4. FUNÇÃO DE SALVAMENTO BLINDADA ---
def forcar_gravacao(aba, df_novo):
    try:
        conn.clear() # Limpa cache antes de escrever
        df_limpo = df_novo.fillna("").astype(str)
        conn.update(worksheet=aba, data=df_limpo)
        st.success(f"✅ Sucesso! Dados atualizados na aba '{aba}'.")
        time.sleep(1)
        st.rerun()
    except Exception as e:
        st.error(f"❌ ERRO AO ESCREVER: {e}")

# --- 5. LOGIN ---
st.sidebar.title("🔐 Acesso OnCall")
user_email = st.sidebar.selectbox("Usuário:", options=["Selecione..."] + sorted(list(dict_users.keys())))
autenticado = False
if user_email != "Selecione...":
    senha_digitada = st.sidebar.text_input("Senha:", type="password")
    if senha_digitada == dict_users.get(user_email, {}).get("senha"): autenticado = True
    elif senha_digitada: st.sidebar.error("Senha incorreta.")

if not autenticado:
    st.info("👈 Faça login na barra lateral.")
    st.stop()

# --- 6. INTERFACE ---
tabs = st.tabs(["📝 Lançar", "📊 Meu Dash", "🛡️ Gerencial (Tabelona)", "📈 BI", "⚙️ Config"]) if user_email in ADMINS else st.tabs(["📝 Lançar", "📊 Meu Dash"])

# === ABA: LANÇAR HORAS ===
with tabs[0]:
    met = st.radio("Método:", ["Dinâmico (+)", "Massa"], horizontal=True)
    if met == "Dinâmico (+)":
        with st.form("form_lancar"):
            st.markdown("### Registrar Atividade")
            df_temp = pd.DataFrame(columns=["projeto", "tipo", "data", "horas", "descricão"])
            df_ed = st.data_editor(df_temp, num_rows="dynamic", use_container_width=True,
                column_config={
                    "projeto": st.column_config.SelectboxColumn("Projeto", options=lista_projetos, required=True),
                    "tipo": st.column_config.SelectboxColumn("Tipo", options=["Front-end", "Back-end", "Banco de Dados", "Infra", "Testes", "Reunião", "Outros"], required=True),
                    "data": st.column_config.DateColumn("Data", default=datetime.now()),
                    "horas": st.column_config.NumberColumn("Horas", min_value=0.5, step=0.5),
                    "descricão": st.column_config.TextColumn("Descrição")
                })
            if st.form_submit_button("🚀 Gravar na Planilha"):
                if not df_ed.empty:
                    v_h = dict_users[user_email]["valor"]
                    novos = []
                    for _, r in df_ed.iterrows():
                        if pd.isna(r["projeto"]) or r["projeto"] == "": continue
                        novos.append({
                            "id": str(uuid.uuid4()), "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "colaborador_email": user_email, "projeto": r["projeto"], "horas": str(r["horas"]),
                            "status_aprovaca": "Pendente", "data_decisao": "", 
                            "competencia": r["data"].strftime("%Y-%m") if hasattr(r["data"], 'strftime') else str(r["data"])[:7], 
                            "tipo": r["tipo"], "descricão": r["descricão"], "email_enviado": "", "valor_hora_historico": str(v_h)
                        })
                    if novos:
                        df_total = pd.concat([df_lan, pd.DataFrame(novos)], ignore_index=True)
                        forcar_gravacao("lancamentos", df_total)
    else:
        arq = st.file_uploader("CSV/Excel", type=["csv", "xlsx"])
        if arq and st.button("Confirmar Importação"):
            df_m = pd.read_csv(arq) if arq.name.endswith('.csv') else pd.read_excel(arq)
            v_h = dict_users[user_email]["valor"]
            novos_m = [{"id": str(uuid.uuid4()), "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "colaborador_email": user_email, "projeto": r["projeto"], "horas": str(r["horas"]), "status_aprovaca": "Pendente", "data_decisao": "", "competencia": str(r["data"])[:7], "tipo": r["tipo"], "descricão": r["descricão"], "email_enviado": "", "valor_hora_historico": str(v_h)} for _, r in df_m.iterrows()]
            forcar_gravacao("lancamentos", pd.concat([df_lan, pd.DataFrame(novos_m)], ignore_index=True))

# === ABA: MEU DASHBOARD (A TABELONA DO USUÁRIO) ===
with tabs[1]:
    meus = df_lan[df_lan["colaborador_email"] == user_email].copy()
    meus["horas"] = pd.to_numeric(meus["horas"], errors="coerce").fillna(0)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Aprovadas", f"{meus[meus['status_aprovaca'] == 'Aprovado']['horas'].sum():.1f}h")
    c2.metric("Pagas", f"{meus[meus['status_aprovaca'] == 'Pago']['horas'].sum():.1f}h")
    c3.metric("Pendentes", f"{meus[meus['status_aprovaca'] == 'Pendente']['horas'].sum():.1f}h")
    c4.metric("Rejeitadas", f"{meus[meus['status_aprovaca'] == 'Rejeitado']['horas'].sum():.1f}h")
    
    st.markdown("### 📋 Meus Registros")
    st.dataframe(meus.sort_values("data_registro", ascending=False), use_container_width=True, hide_index=True)

# === ABA: GERENCIAL (A TABELONA GERAL) ===
if user_email in ADMINS:
    with tabs[2]:
        s1, s2 = st.tabs(["📋 Listagem Geral (Tabelona)", "💰 Pagamentos"])
        with s1:
            st.markdown("### Controle de Aprovações")
            with st.form("form_admin"):
                # AQUI ESTÁ A TABELONA
                df_edit = st.data_editor(df_lan, num_rows="dynamic", use_container_width=True)
                if st.form_submit_button("💾 Salvar Alterações na Tabelona"):
                    forcar_gravacao("lancamentos", df_edit)
        with s2:
            mes = st.selectbox("Competência:", sorted(df_lan["competencia"].unique(), reverse=True))
            df_pg = df_lan[(df_lan["competencia"] == mes) & (df_lan["status_aprovaca"] == "Aprovado")].copy()
            df_pg["horas"] = pd.to_numeric(df_pg["horas"], errors="coerce").fillna(0)
            df_pg["v_h"] = pd.to_numeric(df_pg["valor_hora_historico"], errors="coerce").fillna(
                df_pg["colaborador_email"].map(lambda x: dict_users.get(x, {}).get("valor", 0))
            )
            df_pg["total"] = df_pg["v_h"] * df_pg["horas"]
            
            st.dataframe(df_pg.groupby("colaborador_email")["total"].sum().reset_index(), use_container_width=True)
            
            if st.button(f"Pagar Tudo de {mes}"):
                df_lan.loc[(df_lan["competencia"] == mes) & (df_lan["status_aprovaca"] == "Aprovado"), "status_aprovaca"] = "Pago"
                forcar_gravacao("lancamentos", df_lan)

    with tabs[3]: # BI
        f_mes = st.multiselect("Meses:", sorted(df_lan["competencia"].unique()), default=sorted(df_lan["competencia"].unique()))
        df_bi = df_lan[df_lan["competencia"].isin(f_mes)].copy()
        df_bi["horas"] = pd.to_numeric(df_bi["horas"], errors="coerce").fillna(0)
        df_bi["v_h"] = pd.to_numeric(df_bi["valor_hora_historico"], errors="coerce").fillna(df_bi["colaborador_email"].map(lambda x: dict_users.get(x, {}).get("valor", 0)))
        df_bi["custo"] = df_bi["horas"] * df_bi["v_h"]
        val = df_bi[df_bi["status_aprovaca"].isin(["Aprovado", "Pago"])]
        m1, m2 = st.columns(2)
        m1.metric("Investimento", f"R$ {val['custo'].sum():,.2f}")
        m2.metric("Horas", f"{val['horas'].sum():.1f}h")
        g1, g2 = st.columns(2)
        with g1: st.bar_chart(val.groupby("projeto")["custo"].sum())
        with g2: st.bar_chart(val.groupby("tipo")["horas"].sum())

    with tabs[4]: # CONFIGURAÇÕES
        u_t, p_t = st.tabs(["👥 Usuários", "🏗️ Projetos"])
        with u_t:
            with st.form("f_users"):
                ed_u = st.data_editor(df_u_raw, num_rows="dynamic", use_container_width=True)
                if st.form_submit_button("💾 Salvar Usuários"):
                    forcar_gravacao("config_usuarios", ed_u.dropna(subset=["emails_autorizados"]))
        with p_t:
            with st.form("f_projs"):
                ed_p = st.data_editor(df_p_raw, num_rows="dynamic", use_container_width=True)
                if st.form_submit_button("💾 Salvar Projetos"):
                    forcar_gravacao("config_projetos", ed_p.dropna(subset=["projetos"]))