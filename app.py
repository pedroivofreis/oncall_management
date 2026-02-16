import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid
import time

# Configuração da Página
st.set_page_config(page_title="Oncall Management - v11.2", layout="wide", page_icon="🚀")

# --- 1. CONEXÃO ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 2. CARREGAMENTO COM BLINDAGEM ---
try:
    conn.clear() # Limpa o cache para ler o dado REAL do Google
    
    # Lê as abas
    df_p_raw = conn.read(worksheet="config_projetos", ttl=0)
    df_u_raw = conn.read(worksheet="config_usuarios", ttl=0)
    df_lan = conn.read(worksheet="lancamentos", ttl=0)

    # === TRAVA DE SEGURANÇA (O SALVA-VIDAS) ===
    # Se a leitura vier sem as colunas principais, o app TRAVA e avisa, para não salvar errado.
    colunas_obrigatorias = ["projeto", "horas", "colaborador_email"]
    
    # Normaliza nomes para verificação (tudo minúsculo)
    cols_atuais = [c.strip().lower() for c in df_lan.columns]
    
    # Verifica se as colunas essenciais existem
    if not set(colunas_obrigatorias).issubset(cols_atuais):
        st.error("🚨 PARE TUDO! O sistema detectou que os cabeçalhos da planilha sumiram.")
        st.warning("Para evitar perda de dados, a gravação foi bloqueada. Vá no Google Sheets e restaure a Linha 1.")
        st.stop() # Mata o app aqui. Ele não roda o resto, logo não salva nada errado.

    # Normaliza o DataFrame para uso
    df_lan.columns = [c.strip().lower() for c in df_lan.columns]
    
    # Garante colunas técnicas (sem apagar as outras)
    for col in ['email_enviado', 'valor_hora_historico']:
        if col not in df_lan.columns:
            df_lan[col] = ""

except Exception as e:
    st.error(f"Erro Crítico de Leitura: {e}")
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

# --- 4. FUNÇÃO DE SALVAR (CORRIGIDA) ---
def salvar_blindado(aba, dataframe):
    try:
        # Verifica se o DF tem colunas antes de salvar
        if dataframe.columns.empty:
            st.error("Erro: Tentativa de salvar tabela sem colunas. Operação cancelada.")
            return

        conn.clear()
        # fillna("") é vital para não mandar células 'quebradas'
        conn.update(worksheet=aba, data=dataframe.fillna("").astype(str))
        st.success(f"✅ Dados gravados com sucesso em '{aba}'!")
        time.sleep(1)
        st.rerun()
    except Exception as e:
        st.error(f"❌ Erro ao gravar: {e}")

# --- 5. LOGIN ---
st.sidebar.title("🔐 Acesso OnCall")
user_email = st.sidebar.selectbox("Usuário:", options=["Selecione..."] + sorted(list(dict_users.keys())))
autenticado = False
if user_email != "Selecione...":
    senha = st.sidebar.text_input("Senha:", type="password")
    if senha == dict_users.get(user_email, {}).get("senha"): autenticado = True
    elif senha: st.sidebar.error("Senha incorreta.")

if not autenticado:
    st.info("👈 Faça login.")
    st.stop()

# --- 6. INTERFACE ---
tabs = st.tabs(["📝 Lançar", "📊 Dash", "🛡️ Admin", "📈 BI", "⚙️ Config"]) if user_email in ADMINS else st.tabs(["📝 Lançar", "📊 Dash"])

# === ABA: LANÇAR ===
with tabs[0]:
    met = st.radio("Método:", ["Dinâmico", "Massa"], horizontal=True)
    if met == "Dinâmico":
        with st.form("f_lan"):
            st.markdown("### Registrar Atividade")
            df_ed = st.data_editor(pd.DataFrame(columns=["projeto","tipo","data","horas","descricão"]), num_rows="dynamic", use_container_width=True,
                column_config={"projeto": st.column_config.SelectboxColumn(options=lista_projetos, required=True),
                               "tipo": st.column_config.SelectboxColumn(options=["Front-end","Back-end","Banco de Dados","Infra","Testes","Reunião","Outros"]),
                               "data": st.column_config.DateColumn(default=datetime.now()),
                               "horas": st.column_config.NumberColumn(min_value=0.5, step=0.5)})
            if st.form_submit_button("🚀 Gravar"):
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
                        # Concatena com a base existente para não perder o que já tem
                        df_final = pd.concat([df_lan, pd.DataFrame(novos)], ignore_index=True)
                        salvar_blindado("lancamentos", df_final)
    else:
        arq = st.file_uploader("CSV/Excel")
        if arq and st.button("Importar"):
            df_m = pd.read_csv(arq) if arq.name.endswith('.csv') else pd.read_excel(arq)
            novos = [{"id": str(uuid.uuid4()), "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "colaborador_email": user_email, "projeto": r["projeto"], "horas": str(r["horas"]), "status_aprovaca": "Pendente", "data_decisao": "", "competencia": str(r["data"])[:7], "tipo": r["tipo"], "descricão": r["descricão"], "email_enviado": "", "valor_hora_historico": str(dict_users[user_email]["valor"])} for _, r in df_m.iterrows()]
            salvar_blindado("lancamentos", pd.concat([df_lan, pd.DataFrame(novos)], ignore_index=True))

# === ABA: DASHBOARD ===
with tabs[1]:
    meus = df_lan[df_lan["colaborador_email"] == user_email].copy()
    meus["horas"] = pd.to_numeric(meus["horas"], errors="coerce").fillna(0)
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Aprovado", f"{meus[meus['status_aprovaca']=='Aprovado']['horas'].sum():.1f}h")
    c2.metric("Pago", f"{meus[meus['status_aprovaca']=='Pago']['horas'].sum():.1f}h")
    c3.metric("Pendente", f"{meus[meus['status_aprovaca']=='Pendente']['horas'].sum():.1f}h")
    c4.metric("Rejeitado", f"{meus[meus['status_aprovaca']=='Rejeitado']['horas'].sum():.1f}h")
    st.dataframe(meus.sort_values("data_registro", ascending=False), use_container_width=True, hide_index=True)

# === ABA: ADMIN & BI ===
if user_email in ADMINS:
    with tabs[2]: # Admin
        s1, s2 = st.tabs(["Geral", "Pagamentos"])
        with s1:
            with st.form("f_adm"):
                df_edt = st.data_editor(df_lan, num_rows="dynamic", use_container_width=True)
                if st.form_submit_button("Salvar Geral"): salvar_blindado("lancamentos", df_edt)
        with s2:
            mes = st.selectbox("Mês:", sorted(df_lan["competencia"].unique(), reverse=True))
            if st.button(f"Pagar {mes}"):
                df_lan.loc[(df_lan["competencia"]==mes) & (df_lan["status_aprovaca"]=="Aprovado"), "status_aprovaca"] = "Pago"
                salvar_blindado("lancamentos", df_lan)

    with tabs[3]: # BI
        df_bi = df_lan.copy()
        df_bi["horas"] = pd.to_numeric(df_bi["horas"], errors="coerce").fillna(0)
        df_bi["custo"] = df_bi["horas"] * pd.to_numeric(df_bi["valor_hora_historico"], errors="coerce").fillna(0)
        val = df_bi[df_bi["status_aprovaca"].isin(["Aprovado","Pago"])]
        c1, c2 = st.columns(2)
        c1.metric("R$ Total", f"R$ {val['custo'].sum():,.2f}")
        c2.metric("Horas", f"{val['horas'].sum():.1f}h")
        st.bar_chart(val.groupby("projeto")["custo"].sum())

    with tabs[4]: # Config
        c1, c2 = st.tabs(["Usuários", "Projetos"])
        with c1:
            with st.form("fu"):
                du = st.data_editor(df_u_raw, num_rows="dynamic", use_container_width=True)
                if st.form_submit_button("Salvar"): salvar_blindado("config_usuarios", du.dropna(subset=["emails_autorizados"]))
        with c2:
            with st.form("fp"):
                dp = st.data_editor(df_p_raw, num_rows="dynamic", use_container_width=True)
                if st.form_submit_button("Salvar"): salvar_blindado("config_projetos", dp.dropna(subset=["projetos"]))