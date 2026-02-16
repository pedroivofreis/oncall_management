import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid
import time
import io

# Configuração da Página
st.set_page_config(page_title="Oncall Management - v10.0", layout="wide", page_icon="🚀")

# --- 1. CONEXÃO ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 2. CARREGAMENTO ---
try:
    # Lendo as abas separadas
    df_p_raw = conn.read(worksheet="config_projetos", ttl=0).dropna(how="all")
    df_u_raw = conn.read(worksheet="config_usuarios", ttl=0).dropna(how="all")
    df_lan = conn.read(worksheet="lancamentos", ttl=0).dropna(how="all")
    
    # Normalização de colunas
    df_lan.columns = [c.strip().lower() for c in df_lan.columns]
    
    # Blindagem de colunas para o funcionamento do sistema e BI
    for col in ['email_enviado', 'valor_hora_historico']:
        if col not in df_lan.columns:
            df_lan[col] = ""
except Exception as e:
    st.error(f"Erro Crítico de Carregamento: {e}. Verifique as abas da planilha.")
    st.stop()

# --- 3. PROCESSAMENTO DE CONFIGS ---
lista_projetos = df_p_raw["projetos"].dropna().astype(str).str.strip().unique().tolist()

dict_users = {}
for _, row in df_u_raw.dropna(subset=["emails_autorizados"]).iterrows():
    dict_users[row["emails_autorizados"].strip()] = {
        "valor": pd.to_numeric(row["valor_hora"], errors='coerce') or 0,
        "senha": str(row["senhas"]).strip()
    }

ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

# --- 4. LOGIN ---
st.sidebar.title("🔐 Acesso OnCall")
user_email = st.sidebar.selectbox("Usuário:", options=["Selecione..."] + sorted(list(dict_users.keys())))
autenticado = False

if user_email != "Selecione...":
    senha_digitada = st.sidebar.text_input("Senha:", type="password")
    if senha_digitada == dict_users.get(user_email, {}).get("senha"):
        autenticado = True
    elif senha_digitada:
        st.sidebar.error("Senha incorreta.")

if not autenticado:
    st.info("👈 Identifique-se na lateral para acessar o sistema.")
    st.stop()

# --- 5. INTERFACE (TABS COMPLETAS) ---
t_list = ["📝 Lançar", "📊 Meu Dash"]
if user_email in ADMINS:
    t_list += ["🛡️ Gerencial", "📈 BI Financeiro", "⚙️ Config"]
tabs = st.tabs(t_list)

# === ABA: LANÇAR HORAS ===
with tabs[0]:
    met = st.radio("Método:", ["Dinâmico (+)", "Massa (CSV/Excel)"], horizontal=True)
    
    if met == "Dinâmico (+)":
        with st.form("form_lan_v10"):
            st.markdown("### Adicione suas atividades:")
            df_temp = pd.DataFrame(columns=["projeto", "tipo", "data", "horas", "descricão"])
            df_ed = st.data_editor(df_temp, num_rows="dynamic", use_container_width=True,
                column_config={
                    "projeto": st.column_config.SelectboxColumn("Projeto", options=lista_projetos, required=True),
                    "tipo": st.column_config.SelectboxColumn("Tipo", options=["Front-end", "Back-end", "Banco de Dados", "Infra", "Testes", "Reunião", "Outros"], required=True),
                    "data": st.column_config.DateColumn("Data", default=datetime.now()),
                    "horas": st.column_config.NumberColumn("Horas", min_value=0.5, step=0.5),
                    "descricão": st.column_config.TextColumn("Descrição")
                })
            submit_lan = st.form_submit_button("🚀 Gravar Lançamentos na Planilha")
            
        if submit_lan:
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
                    df_final = pd.concat([df_lan, pd.DataFrame(novos)], ignore_index=True).fillna("").astype(str)
                    conn.update(worksheet="lancamentos", data=df_final)
                    st.success("✅ Lançamentos gravados com sucesso!"); time.sleep(1); st.rerun()

    else:
        st.info("Formato esperado: projeto, horas, tipo, descricão, data (YYYY-MM-DD)")
        arq = st.file_uploader("Upload de arquivo", type=["csv", "xlsx"])
        if arq and st.button("Confirmar Importação em Massa"):
            df_m = pd.read_csv(arq) if arq.name.endswith('.csv') else pd.read_excel(arq)
            v_h = dict_users[user_email]["valor"]
            novos_m = []
            for _, r in df_m.iterrows():
                novos_m.append({
                    "id": str(uuid.uuid4()), "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "colaborador_email": user_email, "projeto": r["projeto"], "horas": str(r["horas"]),
                    "status_aprovaca": "Pendente", "data_decisao": "", 
                    "competencia": str(r["data"])[:7], "tipo": r["tipo"], "descricão": r["descricão"], 
                    "email_enviado": "", "valor_hora_historico": str(v_h)
                })
            df_final = pd.concat([df_lan, pd.DataFrame(novos_m)], ignore_index=True).fillna("").astype(str)
            conn.update(worksheet="lancamentos", data=df_final)
            st.success("✅ Importação concluída!"); time.sleep(1); st.rerun()

# === ABA: MEU DASHBOARD (COLABORADOR) ===
with tabs[1]:
    meus = df_lan[df_lan["colaborador_email"] == user_email].copy()
    meus["horas"] = pd.to_numeric(meus["horas"], errors="coerce").fillna(0)
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Aprovadas", f"{meus[meus['status_aprovaca'] == 'Aprovado']['horas'].sum():.1f}h")
    c2.metric("Pagas", f"{meus[meus['status_aprovaca'] == 'Pago']['horas'].sum():.1f}h")
    c3.metric("Pendentes", f"{meus[meus['status_aprovaca'] == 'Pendente']['horas'].sum():.1f}h")
    c4.metric("Rejeitadas", f"{meus[meus['status_aprovaca'] == 'Rejeitado']['horas'].sum():.1f}h")
    
    st.divider()
    st.subheader("Histórico de Lançamentos")
    st.dataframe(meus.sort_values("data_registro", ascending=False), use_container_width=True, hide_index=True)

# === ÁREA ADMIN ===
if user_email in ADMINS:
    with tabs[2]: # GERENCIAL & FINANCEIRO
        s1, s2 = st.tabs(["✓ Aprovações", "💰 Financeiro (Pagamentos)"])
        with s1:
            with st.form("form_gerencial"):
                df_ed_ger = st.data_editor(df_lan, hide_index=True, use_container_width=True)
                save_ger = st.form_submit_button("💾 Salvar Alterações Gerenciais")
            if save_ger:
                conn.update(worksheet="lancamentos", data=df_ed_ger.fillna("").astype(str))
                st.success("✅ Planilha Master atualizada!"); time.sleep(1); st.rerun()
        with s2:
            mes = st.selectbox("Selecione a Competência:", sorted(df_lan["competencia"].unique(), reverse=True))
            df_p = df_lan[(df_lan["competencia"] == mes) & (df_lan["status_aprovaca"] == "Aprovado")].copy()
            df_p["horas"] = pd.to_numeric(df_p["horas"], errors="coerce").fillna(0)
            df_p["v_h"] = pd.to_numeric(df_p["valor_hora_historico"], errors="coerce").fillna(
                df_p["colaborador_email"].map(lambda x: dict_users.get(x, {}).get("valor", 0))
            )
            df_p["total"] = df_p["v_h"] * df_p["horas"]
            
            resumo_pag = df_p.groupby("colaborador_email")["total"].sum().reset_index()
            st.dataframe(resumo_pag.style.format({"total": "R$ {:.2f}"}), use_container_width=True)
            
            if st.button(f"Confirmar Pagamento Total de {mes}"):
                df_lan.loc[(df_lan["competencia"] == mes) & (df_lan["status_aprovaca"] == "Aprovado"), "status_aprovaca"] = "Pago"
                conn.update(worksheet="lancamentos", data=df_lan.fillna("").astype(str))
                st.success(f"Status atualizado para PAGO em {mes}!"); time.sleep(1); st.rerun()

    with tabs[3]: # BI FINANCEIRO COMPLETO
        st.subheader("📊 Inteligência Financeira")
        f_mes = st.multiselect("Filtrar Período:", sorted(df_lan["competencia"].unique()), default=sorted(df_lan["competencia"].unique()))
        df_bi = df_lan[df_lan["competencia"].isin(f_mes)].copy()
        df_bi["horas"] = pd.to_numeric(df_bi["horas"], errors="coerce").fillna(0)
        df_bi["v_h"] = pd.to_numeric(df_bi["valor_hora_historico"], errors="coerce").fillna(
            df_bi["colaborador_email"].map(lambda x: dict_users.get(x, {}).get("valor", 0))
        )
        df_bi["custo"] = df_bi["horas"] * df_bi["v_h"]
        
        # Considera Aprovados e Pagos para custo real
        val = df_bi[df_bi["status_aprovaca"].isin(["Aprovado", "Pago"])]
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Investimento Total", f"R$ {val['custo'].sum():,.2f}")
        m2.metric("Horas Totais", f"{val['horas'].sum():.1f}h")
        m3.metric("Ticket Médio/h", f"R$ {(val['custo'].sum()/val['horas'].sum() if val['horas'].sum()>0 else 0):,.2f}")
        
        st.divider()
        g1, g2 = st.columns(2)
        with g1:
            st.markdown("### 🏗️ Custo por Projeto")
            st.bar_chart(val.groupby("projeto")["custo"].sum(), color="#2e7d32")
        with g2:
            st.markdown("### 🛠️ Horas por Tipo")
            st.bar_chart(val.groupby("tipo")["horas"].sum(), color="#29b5e8")

    with tabs[4]: # CONFIGURAÇÕES (SUB-TABS)
        st.info("Gerencie usuários e projetos de forma independente.")
        c_u, c_p = st.tabs(["👥 Usuários & Valores", "🏗️ Projetos"])
        with c_u:
            with st.form("form_usuarios_v10"):
                ed_u = st.data_editor(df_u_raw, num_rows="dynamic", hide_index=True, use_container_width=True)
                save_u = st.form_submit_button("💾 Salvar Alterações de Usuários")
            if save_u:
                conn.update(worksheet="config_usuarios", data=ed_u.dropna(subset=["emails_autorizados"]).fillna("").astype(str))
                st.success("✅ Usuários atualizados!"); time.sleep(1); st.rerun()
        with c_p:
            with st.form("form_projetos_v10"):
                ed_p = st.data_editor(df_p_raw, num_rows="dynamic", hide_index=True, use_container_width=True)
                save_p = st.form_submit_button("💾 Salvar Alterações de Projetos")
            if save_p:
                conn.update(worksheet="config_projetos", data=ed_p.dropna(subset=["projetos"]).fillna("").astype(str))
                st.success("✅ Lista de projetos atualizada!"); time.sleep(1); st.rerun()

# --- RODAPÉ ---
st.markdown("---")
st.markdown(f"<p style='text-align: center; color: grey;'>Projeto by <b>Pedro Reis</b> | OnCall Management v10.0</p>", unsafe_allow_html=True)