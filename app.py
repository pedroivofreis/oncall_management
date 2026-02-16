import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid
import time

# Configuração da Página
st.set_page_config(page_title="Oncall Management - v12.0 Auto-Repair", layout="wide", page_icon="🚑")

# --- 1. CONEXÃO ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 2. CARREGAMENTO COM AUTO-REPARO (A CURA) ---
def carregar_dados_blindados():
    try:
        conn.clear() # Limpa cache
        
        # Tenta ler as abas
        try:
            df_lan = conn.read(worksheet="lancamentos", ttl=0)
            df_u_raw = conn.read(worksheet="config_usuarios", ttl=0)
            df_p_raw = conn.read(worksheet="config_projetos", ttl=0)
        except:
            st.error("Erro de conexão inicial. Verifique se as abas existem.")
            st.stop()

        # === AUTO-REPARO DA ABA LANÇAMENTOS ===
        # Colunas oficiais que DEVEM existir
        cols_oficiais = [
            "id", "data_registro", "colaborador_email", "projeto", "horas", 
            "status_aprovaca", "data_decisao", "competencia", "tipo", 
            "descricão", "email_enviado", "valor_hora_historico"
        ]
        
        # Verifica se as colunas lidas batem com as oficiais
        cols_atuais = [str(c).strip().lower() for c in df_lan.columns]
        
        # Se não encontrar 'projeto' ou 'horas' ou 'email', assume que o cabeçalho explodiu
        if "projeto" not in cols_atuais or "horas" not in cols_atuais:
            st.warning("⚠️ ALERTA: O sistema detectou que a Linha 1 (Cabeçalho) sumiu ou está incorreta.")
            with st.spinner("🚑 Aplicando AUTO-REPARO: Restaurando cabeçalhos originais..."):
                # Cria um DataFrame vazio APENAS com os cabeçalhos certos
                df_reparo = pd.DataFrame(columns=cols_oficiais)
                # Força a gravação imediata para consertar a planilha
                conn.update(worksheet="lancamentos", data=df_reparo)
                st.success("✅ Planilha Consertada! O sistema irá recarregar.")
                time.sleep(2)
                st.rerun() # Recarrega a página para ler certo dessa vez
        
        # Se chegou aqui, o cabeçalho está ok. Normaliza.
        df_lan.columns = [c.strip().lower() for c in df_lan.columns]
        
        # Garante colunas técnicas
        for col in ['email_enviado', 'valor_hora_historico']:
            if col not in df_lan.columns: df_lan[col] = ""

        return df_lan, df_u_raw, df_p_raw

    except Exception as e:
        st.error(f"Erro Crítico: {e}")
        st.stop()

# Carrega os dados usando a função blindada
df_lan, df_u_raw, df_p_raw = carregar_dados_blindados()

# --- 3. PROCESSAMENTO ---
lista_projetos = df_p_raw["projetos"].dropna().astype(str).str.strip().unique().tolist()
dict_users = {}
for _, row in df_u_raw.dropna(subset=["emails_autorizados"]).iterrows():
    dict_users[row["emails_autorizados"].strip()] = {
        "valor": pd.to_numeric(row["valor_hora"], errors='coerce') or 0,
        "senha": str(row["senhas"]).strip()
    }
ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

# --- 4. FUNÇÃO SALVAR ---
def salvar(aba, df):
    try:
        conn.clear()
        # O index=False não é suportado diretamente por todas as versões da lib, 
        # mas garantimos que o DF está limpo.
        conn.update(worksheet=aba, data=df.fillna("").astype(str))
        st.success(f"✅ Salvo em '{aba}'!")
        time.sleep(1); st.rerun()
    except Exception as e:
        st.error(f"Erro ao salvar: {e}")

# --- 5. LOGIN ---
st.sidebar.title("🚑 OnCall Auto-Repair")
user_email = st.sidebar.selectbox("Usuário:", options=["Selecione..."] + sorted(list(dict_users.keys())))
autenticado = False
if user_email != "Selecione..." and dict_users:
    senha = st.sidebar.text_input("Senha:", type="password")
    if senha == dict_users.get(user_email, {}).get("senha"): autenticado = True
    elif senha: st.sidebar.error("Senha incorreta.")

if not autenticado:
    st.info("👈 Faça login.")
    st.stop()

# --- 6. INTERFACE ---
tabs = st.tabs(["📝 Lançar", "📊 Dash", "🛡️ Admin", "📈 BI", "⚙️ Config"]) if user_email in ADMINS else st.tabs(["📝 Lançar", "📊 Dash"])

# === LANÇAR ===
with tabs[0]:
    met = st.radio("Método:", ["Dinâmico", "Massa"], horizontal=True)
    if met == "Dinâmico":
        with st.form("f_lan"):
            st.markdown("### Novo Lançamento")
            df_ed = st.data_editor(pd.DataFrame(columns=["projeto","tipo","data","horas","descricão"]), num_rows="dynamic", use_container_width=True,
                column_config={"projeto": st.column_config.SelectboxColumn(options=lista_projetos, required=True),
                               "tipo": st.column_config.SelectboxColumn(options=["Front-end","Back-end","Banco de Dados","Infra","Testes","Reunião","Outros"]),
                               "data": st.column_config.DateColumn(default=datetime.now()),
                               "horas": st.column_config.NumberColumn(min_value=0.5, step=0.5)})
            if st.form_submit_button("🚀 Salvar"):
                if not df_ed.empty:
                    novos = []
                    v_h = dict_users[user_email]["valor"]
                    for _, r in df_ed.iterrows():
                        if pd.isna(r["projeto"]): continue
                        novos.append({
                            "id": str(uuid.uuid4()), "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "colaborador_email": user_email, "projeto": r["projeto"], "horas": str(r["horas"]),
                            "status_aprovaca": "Pendente", "data_decisao": "", "competencia": r["data"].strftime("%Y-%m")[:7],
                            "tipo": r["tipo"], "descricão": r["descricão"], "email_enviado": "", "valor_hora_historico": str(v_h)
                        })
                    if novos: salvar("lancamentos", pd.concat([df_lan, pd.DataFrame(novos)], ignore_index=True))
    else:
        arq = st.file_uploader("CSV/Excel")
        if arq and st.button("Importar"):
            df_m = pd.read_csv(arq) if arq.name.endswith('.csv') else pd.read_excel(arq)
            novos = [{"id": str(uuid.uuid4()), "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "colaborador_email": user_email, "projeto": r["projeto"], "horas": str(r["horas"]), "status_aprovaca": "Pendente", "data_decisao": "", "competencia": str(r["data"])[:7], "tipo": r["tipo"], "descricão": r["descricão"], "email_enviado": "", "valor_hora_historico": str(dict_users[user_email]["valor"])} for _, r in df_m.iterrows()]
            salvar("lancamentos", pd.concat([df_lan, pd.DataFrame(novos)], ignore_index=True))

# === DASHBOARD ===
with tabs[1]:
    meus = df_lan[df_lan["colaborador_email"] == user_email].copy()
    meus["horas"] = pd.to_numeric(meus["horas"], errors="coerce").fillna(0)
    st.metric("Total Horas", f"{meus['horas'].sum():.1f}h")
    st.dataframe(meus.sort_values("data_registro", ascending=False), use_container_width=True, hide_index=True)

# === ADMIN ===
if user_email in ADMINS:
    with tabs[2]:
        with st.form("f_adm"):
            df_edt = st.data_editor(df_lan, num_rows="dynamic", use_container_width=True)
            if st.form_submit_button("Salvar Geral"): salvar("lancamentos", df_edt)
    with tabs[3]: # BI
        df_bi = df_lan.copy()
        df_bi["horas"] = pd.to_numeric(df_bi["horas"], errors="coerce").fillna(0)
        df_bi["custo"] = df_bi["horas"] * pd.to_numeric(df_bi["valor_hora_historico"], errors="coerce").fillna(0)
        st.bar_chart(df_bi.groupby("projeto")["custo"].sum())
    with tabs[4]: # CONFIG
        c1, c2 = st.tabs(["Usuários", "Projetos"])
        with c1:
            with st.form("fu"):
                du = st.data_editor(df_u_raw, num_rows="dynamic", use_container_width=True)
                if st.form_submit_button("Salvar"): salvar("config_usuarios", du.dropna(subset=["emails_autorizados"]))
        with c2:
            with st.form("fp"):
                dp = st.data_editor(df_p_raw, num_rows="dynamic", use_container_width=True)
                if st.form_submit_button("Salvar"): salvar("config_projetos", dp.dropna(subset=["projetos"]))