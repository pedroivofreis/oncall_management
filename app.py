import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid
import time

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Oncall Management - v16.0 BUNKER", layout="wide", page_icon="🛡️")

# --- A VERDADE ABSOLUTA (Colunas Fixas) ---
# O sistema jamais confiará na planilha para saber os cabeçalhos.
# Estas colunas são a lei.
COLS_OFICIAIS = [
    "id", "data_registro", "colaborador_email", "projeto", "horas", 
    "status_aprovaca", "data_decisao", "competencia", "tipo", 
    "descricão", "email_enviado", "valor_hora_historico"
]

# --- 1. CONEXÃO ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 2. LEITURA SEGURA ---
def carregar_dados():
    try:
        conn.clear() # Limpa o cache do Streamlit
        
        try:
            df = conn.read(worksheet="lancamentos", ttl=0)
        except:
            # Se der erro de leitura, retorna vazio mas com colunas certas
            return pd.DataFrame(columns=COLS_OFICIAIS)

        # Se o DF vier vazio ou sem colunas, ignora e usa o padrão oficial
        if df.empty or len(df.columns) < 2:
            return pd.DataFrame(columns=COLS_OFICIAIS)
        
        # Normaliza cabeçalhos lidos
        df.columns = [str(c).strip().lower() for c in df.columns]
        
        # Verifica se as colunas batem. Se faltar a principal, recria a estrutura.
        if "projeto" not in df.columns:
            return pd.DataFrame(columns=COLS_OFICIAIS)
            
        # Garante que todas as colunas oficiais existam no DF lido
        for col in COLS_OFICIAIS:
            if col not in df.columns:
                df[col] = ""
                
        # Retorna apenas as colunas oficiais, na ordem certa
        return df[COLS_OFICIAIS]
        
    except Exception as e:
        st.error(f"Erro de conexão: {e}")
        return pd.DataFrame(columns=COLS_OFICIAIS)

# Carrega (mas não salva nada ainda!)
df_lan = carregar_dados()

# Carrega configs auxiliares
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

# --- 4. FUNÇÃO SALVAR (O COFRE) ---
def salvar_cofre(aba, df_input):
    try:
        conn.clear()
        
        # Se for a aba principal, passamos o Pente Fino
        if aba == "lancamentos":
            # 1. Garante colunas
            for col in COLS_OFICIAIS:
                if col not in df_input.columns:
                    df_input[col] = ""
            # 2. Força ordem e descarta lixo
            df_final = df_input[COLS_OFICIAIS]
        else:
            df_final = df_input
            
        # 3. Limpeza final para o Google aceitar
        df_final = df_final.fillna("").astype(str)
        
        conn.update(worksheet=aba, data=df_final)
        st.success(f"✅ Salvo em {aba}!")
        time.sleep(1); st.rerun()
    except Exception as e:
        st.error(f"❌ Erro ao salvar: {e}")

# --- 5. SIDEBAR & LOGIN ---
st.sidebar.title("🛡️ OnCall Bunker")
user_email = st.sidebar.selectbox("Usuário:", options=["Selecione..."] + sorted(list(dict_users.keys())))
autenticado = False

# === BOTÃO DE RECONSTRUÇÃO (USE SE A PLANILHA ZERAR) ===
st.sidebar.markdown("---")
st.sidebar.warning("🛠️ Área de Manutenção")
if st.sidebar.button("🆘 Recriar Cabeçalhos"):
    # Este botão ignora qualquer leitura e grava apenas o cabeçalho oficial
    df_reset = pd.DataFrame(columns=COLS_OFICIAIS)
    salvar_cofre("lancamentos", df_reset)
# ========================================================

if user_email != "Selecione..." and dict_users:
    senha = st.sidebar.text_input("Senha:", type="password")
    if senha == dict_users.get(user_email, {}).get("senha"): autenticado = True
    elif senha: st.sidebar.error("Senha incorreta.")

if not autenticado:
    st.info("👈 Login necessário.")
    st.stop()

# --- 6. INTERFACE ---
tabs = st.tabs(["📝 Lançar", "📊 Dash", "🛡️ Admin", "📈 BI", "⚙️ Config"]) if user_email in ADMINS else st.tabs(["📝 Lançar", "📊 Dash"])

# === ABA: LANÇAR ===
with tabs[0]:
    with st.form("form_lancar"):
        st.markdown("### ⏱️ Novo Lançamento")
        col1, col2 = st.columns(2)
        with col1:
            proj = st.selectbox("Projeto", options=lista_projetos)
            tipo = st.selectbox("Tipo", ["Front-end","Back-end","Banco de Dados","Infra","Testes","Reunião","Outros"])
        with col2:
            data = st.date_input("Data", value=datetime.now())
            horas = st.number_input("Horas", min_value=0.5, step=0.5)
        desc = st.text_area("Descrição")
        
        if st.form_submit_button("🚀 Gravar"):
            v_h = dict_users[user_email]["valor"]
            novo_reg = {
                "id": str(uuid.uuid4()), "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "colaborador_email": user_email, "projeto": proj, "horas": str(horas),
                "status_aprovaca": "Pendente", "data_decisao": "", 
                "competencia": data.strftime("%Y-%m"), "tipo": tipo, "descricão": desc, 
                "email_enviado": "", "valor_hora_historico": str(v_h)
            }
            # Adiciona ao DF atual (mesmo que esteja vazio, o novo terá colunas certas)
            df_save = pd.concat([df_lan, pd.DataFrame([novo_reg])], ignore_index=True)
            salvar_cofre("lancamentos", df_save)

# === ABA: DASHBOARD ===
with tabs[1]:
    # Verifica se a coluna existe antes de filtrar
    if "colaborador_email" in df_lan.columns:
        meus = df_lan[df_lan["colaborador_email"] == user_email].copy()
        meus["horas"] = pd.to_numeric(meus["horas"], errors="coerce").fillna(0)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Aprovado", f"{meus[meus['status_aprovaca']=='Aprovado']['horas'].sum():.1f}h")
        c2.metric("Pago", f"{meus[meus['status_aprovaca']=='Pago']['horas'].sum():.1f}h")
        c3.metric("Pendente", f"{meus[meus['status_aprovaca']=='Pendente']['horas'].sum():.1f}h")
        c4.metric("Rejeitado", f"{meus[meus['status_aprovaca']=='Rejeitado']['horas'].sum():.1f}h")
        st.dataframe(meus.sort_values("data_registro", ascending=False), use_container_width=True, hide_index=True)
    else:
        st.error("⚠️ Planilha ilegível. Use o botão 'Recriar Cabeçalhos' na lateral.")

# === ABA: ADMIN & BI ===
if user_email in ADMINS:
    with tabs[2]:
        t1, t2 = st.tabs(["Geral", "Pagamentos"])
        with t1:
            with st.form("f_adm"):
                # Data Editor protegido
                if not df_lan.empty:
                    df_edt = st.data_editor(df_lan, num_rows="dynamic", use_container_width=True)
                    if st.form_submit_button("Salvar Geral"): salvar_cofre("lancamentos", df_edt)
                else:
                    st.warning("Sem dados para editar.")
                    st.form_submit_button("Atualizar") # Botão dummy
        with t2:
            if "competencia" in df_lan.columns:
                mes = st.selectbox("Mês:", sorted(df_lan["competencia"].unique(), reverse=True))
                if st.button(f"Pagar {mes}"):
                    df_lan.loc[(df_lan["competencia"]==mes) & (df_lan["status_aprovaca"]=="Aprovado"), "status_aprovaca"] = "Pago"
                    salvar_cofre("lancamentos", df_lan)

    with tabs[3]: # BI
        if not df_lan.empty and "horas" in df_lan.columns:
            df_bi = df_lan.copy()
            df_bi["horas"] = pd.to_numeric(df_bi["horas"], errors="coerce").fillna(0)
            df_bi["v_h"] = pd.to_numeric(df_bi["valor_hora_historico"], errors="coerce").fillna(0)
            df_bi["custo"] = df_bi["horas"] * df_bi["v_h"]
            val = df_bi[df_bi["status_aprovaca"].isin(["Aprovado","Pago"])]
            
            c1, c2 = st.columns(2)
            c1.metric("Investimento", f"R$ {val['custo'].sum():,.2f}")
            c2.metric("Horas", f"{val['horas'].sum():.1f}h")
            st.bar_chart(val.groupby("projeto")["custo"].sum())

    with tabs[4]: # CONFIG
        c1, c2 = st.tabs(["Usuários", "Projetos"])
        with c1:
            with st.form("fu"):
                du = st.data_editor(df_u_raw, num_rows="dynamic", use_container_width=True)
                if st.form_submit_button("Salvar Usuários"): salvar_cofre("config_usuarios", du)
        with c2:
            with st.form("fp"):
                dp = st.data_editor(df_p_raw, num_rows="dynamic", use_container_width=True)
                if st.form_submit_button("Salvar Projetos"): salvar_cofre("config_projetos", dp)