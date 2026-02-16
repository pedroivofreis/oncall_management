import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid
import time

# Configuração da Página
st.set_page_config(page_title="Oncall Management - v14.0 Final", layout="wide", page_icon="🛡️")

# --- DEFINIÇÃO BLINDADA DAS COLUNAS (Hardcoded) ---
# Isso garante que o Python NUNCA esqueça quais são as colunas, 
# mesmo que a planilha venha vazia.
COLUNAS_OFICIAIS = [
    "id", "data_registro", "colaborador_email", "projeto", "horas", 
    "status_aprovaca", "data_decisao", "competencia", "tipo", 
    "descricão", "email_enviado", "valor_hora_historico"
]

# --- 1. CONEXÃO ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 2. FUNÇÃO DE LEITURA SEGURA ---
def carregar_dados():
    try:
        conn.clear() # Limpa cache
        
        # Tenta ler
        data = conn.read(worksheet="lancamentos", ttl=0)
        
        # Se vier vazio ou sem colunas, retorna um DF vazio mas com a estrutura certa
        if data.empty or len(data.columns) < 5:
            return pd.DataFrame(columns=COLUNAS_OFICIAIS)
        
        # Normaliza colunas
        data.columns = [str(c).strip().lower() for c in data.columns]
        
        # Verifica se as colunas batem. Se não baterem, força a estrutura.
        if "projeto" not in data.columns:
            st.warning("⚠️ Estrutura de colunas incorreta detectada na leitura.")
            return data # Retorna o que tem, mas o sistema vai avisar
            
        return data
    except Exception as e:
        st.error(f"Erro de conexão: {e}")
        return pd.DataFrame(columns=COLUNAS_OFICIAIS)

# Carrega
df_lan = carregar_dados()

# Carrega configs (com tratamento de erro simples)
try:
    df_u_raw = conn.read(worksheet="config_usuarios", ttl=0)
    df_p_raw = conn.read(worksheet="config_projetos", ttl=0)
except:
    df_u_raw = pd.DataFrame(columns=["emails_autorizados", "valor_hora", "senhas"])
    df_p_raw = pd.DataFrame(columns=["projetos"])

# --- 3. DADOS AUXILIARES ---
lista_projetos = df_p_raw["projetos"].dropna().astype(str).str.strip().unique().tolist()
dict_users = {}
if not df_u_raw.empty:
    for _, row in df_u_raw.dropna(subset=["emails_autorizados"]).iterrows():
        dict_users[row["emails_autorizados"].strip()] = {
            "valor": pd.to_numeric(row["valor_hora"], errors='coerce') or 0,
            "senha": str(row["senhas"]).strip()
        }
ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

# --- 4. FUNÇÃO SALVAR (O SEGREDO DO SUCESSO) ---
def salvar_seguro(aba, df_novo):
    try:
        # GARANTIA FINAL:
        # Antes de salvar, verificamos se as colunas estão lá. 
        # Se não estiverem, nós as recolocamos à força.
        if aba == "lancamentos":
            # Garante que todas as colunas oficiais existam
            for col in COLUNAS_OFICIAIS:
                if col not in df_novo.columns:
                    df_novo[col] = ""
            # Reordena para ficar bonito
            df_novo = df_novo[COLUNAS_OFICIAIS]
        
        conn.clear()
        # O segredo: fillna("") remove nulos e astype(str) garante texto
        conn.update(worksheet=aba, data=df_novo.fillna("").astype(str))
        st.success(f"✅ Salvo com sucesso em '{aba}'!")
        time.sleep(1); st.rerun()
    except Exception as e:
        st.error(f"❌ Erro ao salvar: {e}")

# --- 5. LOGIN ---
st.sidebar.title("🛡️ OnCall v14")
user_email = st.sidebar.selectbox("Usuário:", options=["Selecione..."] + sorted(list(dict_users.keys())))
autenticado = False

# Botão de Emergência (Escondido na sidebar)
st.sidebar.markdown("---")
if st.sidebar.button("🆘 Recriar Cabeçalhos (Emergência)"):
    df_vazio = pd.DataFrame(columns=COLUNAS_OFICIAIS)
    salvar_seguro("lancamentos", df_vazio)

if user_email != "Selecione..." and dict_users:
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
    with st.form("form_lancar"):
        st.markdown("### Novo Lançamento")
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
                    # Concatena, mas garante que df_lan tenha as colunas certas antes
                    df_final = pd.concat([df_lan, pd.DataFrame(novos)], ignore_index=True)
                    salvar_seguro("lancamentos", df_final)

# === ABA: DASHBOARD ===
with tabs[1]:
    # Proteção contra KeyError se a coluna não existir
    if "colaborador_email" in df_lan.columns:
        meus = df_lan[df_lan["colaborador_email"] == user_email].copy()
        meus["horas"] = pd.to_numeric(meus["horas"], errors="coerce").fillna(0)
        st.metric("Total Horas", f"{meus['horas'].sum():.1f}h")
        st.dataframe(meus.sort_values("data_registro", ascending=False), use_container_width=True, hide_index=True)
    else:
        st.error("⚠️ Erro de leitura: Coluna 'colaborador_email' não encontrada. Use o botão de emergência na lateral.")

# === ABA: ADMIN & BI ===
if user_email in ADMINS:
    with tabs[2]:
        with st.form("f_adm"):
            df_edt = st.data_editor(df_lan, num_rows="dynamic", use_container_width=True)
            if st.form_submit_button("Salvar Geral"): salvar_seguro("lancamentos", df_edt)
            
    with tabs[3]: # BI
        if "horas" in df_lan.columns and "valor_hora_historico" in df_lan.columns:
            df_bi = df_lan.copy()
            df_bi["horas"] = pd.to_numeric(df_bi["horas"], errors="coerce").fillna(0)
            df_bi["custo"] = df_bi["horas"] * pd.to_numeric(df_bi["valor_hora_historico"], errors="coerce").fillna(0)
            st.bar_chart(df_bi.groupby("projeto")["custo"].sum())
        else:
            st.warning("Dados insuficientes para BI.")

    with tabs[4]: # CONFIG
        c1, c2 = st.tabs(["Usuários", "Projetos"])
        with c1:
            with st.form("fu"):
                du = st.data_editor(df_u_raw, num_rows="dynamic", use_container_width=True)
                if st.form_submit_button("Salvar"): salvar_seguro("config_usuarios", du.dropna(subset=["emails_autorizados"]))
        with c2:
            with st.form("fp"):
                dp = st.data_editor(df_p_raw, num_rows="dynamic", use_container_width=True)
                if st.form_submit_button("Salvar"): salvar_seguro("config_projetos", dp.dropna(subset=["projetos"]))