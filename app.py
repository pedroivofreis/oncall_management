import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid
import time

# --- CONFIGURAÇÃO INICIAL ---
st.set_page_config(page_title="Oncall Management - v15.0 Final", layout="wide", page_icon="🚀")

# --- LISTA MESTRA DE COLUNAS (A BLINDAGEM) ---
# O sistema agora IGNORA se a planilha vier vazia. Ele usa isso aqui como verdade absoluta.
COLS_OFICIAIS = [
    "id", "data_registro", "colaborador_email", "projeto", "horas", 
    "status_aprovaca", "data_decisao", "competencia", "tipo", 
    "descricão", "email_enviado", "valor_hora_historico"
]

# --- 1. CONEXÃO ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 2. LEITURA INTELIGENTE ---
def carregar_dados():
    try:
        conn.clear() # Limpa memória velha
        
        # Tenta ler a aba principal
        try:
            df = conn.read(worksheet="lancamentos", ttl=0)
        except Exception:
            # Se der erro de leitura (429), cria um vazio com a estrutura certa
            return pd.DataFrame(columns=COLS_OFICIAIS)

        # Se vier vazio ou quebrado, força a estrutura oficial
        if df.empty or len(df.columns) < 5:
            return pd.DataFrame(columns=COLS_OFICIAIS)
        
        # Normaliza nomes
        df.columns = [str(c).strip().lower() for c in df.columns]
        
        # Garante que todas as colunas oficiais existam no DF
        for col in COLS_OFICIAIS:
            if col not in df.columns:
                df[col] = ""
                
        return df[COLS_OFICIAIS] # Retorna ordenado e bonitinho
        
    except Exception as e:
        st.error(f"Erro de Conexão: {e}")
        return pd.DataFrame(columns=COLS_OFICIAIS)

# Carrega os dados
df_lan = carregar_dados()

# Carrega configs (com fallback para não travar)
try:
    df_u_raw = conn.read(worksheet="config_usuarios", ttl=0)
    df_p_raw = conn.read(worksheet="config_projetos", ttl=0)
except:
    df_u_raw = pd.DataFrame(columns=["emails_autorizados", "valor_hora", "senhas"])
    df_p_raw = pd.DataFrame(columns=["projetos"])

# --- 3. PROCESSAMENTO ---
lista_projetos = df_p_raw["projetos"].dropna().astype(str).str.strip().unique().tolist()
dict_users = {}
if not df_u_raw.empty:
    for _, row in df_u_raw.dropna(subset=["emails_autorizados"]).iterrows():
        dict_users[row["emails_autorizados"].strip()] = {
            "valor": pd.to_numeric(row["valor_hora"], errors='coerce') or 0,
            "senha": str(row["senhas"]).strip()
        }
ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

# --- 4. FUNÇÃO SALVAR (O TRATOR SEGURO) ---
def salvar_seguro(aba, df_para_salvar):
    try:
        conn.clear()
        
        # SE FOR A ABA DE LANÇAMENTOS, APLICAMOS A CURA
        if aba == "lancamentos":
            # Garante que as colunas existem antes de enviar
            for col in COLS_OFICIAIS:
                if col not in df_para_salvar.columns:
                    df_para_salvar[col] = ""
            # Força a ordem correta das colunas (RECRIA O CABEÇALHO)
            df_para_salvar = df_para_salvar[COLS_OFICIAIS]
            
        # Converte tudo para string para o Google não reclamar
        df_limpo = df_para_salvar.fillna("").astype(str)
        
        conn.update(worksheet=aba, data=df_limpo)
        st.toast(f"✅ Dados salvos com sucesso em {aba}!", icon="🎉")
        time.sleep(1)
        st.rerun()
    except Exception as e:
        st.error(f"❌ Erro ao salvar: {e}")

# --- 5. LOGIN E SIDEBAR ---
st.sidebar.title("🚀 OnCall Manager")
user_email = st.sidebar.selectbox("Usuário:", options=["Selecione..."] + sorted(list(dict_users.keys())))
autenticado = False

# === BOTÃO DE EMERGÊNCIA (SALVA-VIDAS) ===
st.sidebar.divider()
if st.sidebar.button("🚑 REPARAR CABEÇALHOS"):
    # Envia um DataFrame vazio mas com as colunas certas. 
    # Isso desenha a linha 1 de volta na marra.
    df_reparo = pd.DataFrame(columns=COLS_OFICIAIS)
    salvar_seguro("lancamentos", df_reparo)
# ==========================================

if user_email != "Selecione..." and dict_users:
    senha = st.sidebar.text_input("Senha:", type="password")
    if senha == dict_users.get(user_email, {}).get("senha"): autenticado = True
    elif senha: st.sidebar.error("Senha incorreta.")

if not autenticado:
    st.info("👈 Faça login para começar.")
    st.stop()

# --- 6. INTERFACE COMPLETA (VOLTAMOS COM TUDO!) ---
tabs_list = ["📝 Lançar", "📊 Meu Dash"]
if user_email in ADMINS:
    tabs_list += ["🛡️ Gerencial", "📈 BI Financeiro", "⚙️ Config"]
tabs = st.tabs(tabs_list)

# === ABA 1: LANÇAR ===
with tabs[0]:
    met = st.radio("Método:", ["Dinâmico", "Massa (Excel)"], horizontal=True)
    if met == "Dinâmico":
        with st.form("form_lancar"):
            st.markdown("### ⏱️ Novo Registro")
            col1, col2 = st.columns(2)
            with col1:
                proj = st.selectbox("Projeto", options=lista_projetos)
                tipo = st.selectbox("Tipo", ["Front-end","Back-end","Banco de Dados","Infra","Testes","Reunião","Outros"])
            with col2:
                data = st.date_input("Data", value=datetime.now())
                horas = st.number_input("Horas", min_value=0.5, step=0.5)
            desc = st.text_area("Descrição")
            
            if st.form_submit_button("🚀 Gravar Registro"):
                v_h = dict_users[user_email]["valor"]
                novo = {
                    "id": str(uuid.uuid4()), "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "colaborador_email": user_email, "projeto": proj, "horas": str(horas),
                    "status_aprovaca": "Pendente", "data_decisao": "", 
                    "competencia": data.strftime("%Y-%m"), "tipo": tipo, "descricão": desc, 
                    "email_enviado": "", "valor_hora_historico": str(v_h)
                }
                # Adiciona ao DF existente e salva
                df_final = pd.concat([df_lan, pd.DataFrame([novo])], ignore_index=True)
                salvar_seguro("lancamentos", df_final)

    else: # Importação em massa
        arq = st.file_uploader("Arquivo Excel/CSV", type=["csv", "xlsx"])
        if arq and st.button("Importar"):
            df_m = pd.read_csv(arq) if arq.name.endswith('.csv') else pd.read_excel(arq)
            v_h = dict_users[user_email]["valor"]
            novos = []
            for _, r in df_m.iterrows():
                novos.append({
                    "id": str(uuid.uuid4()), "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "colaborador_email": user_email, "projeto": r["projeto"], "horas": str(r["horas"]),
                    "status_aprovaca": "Pendente", "data_decisao": "", "competencia": str(r["data"])[:7], 
                    "tipo": r["tipo"], "descricão": r["descricão"], "email_enviado": "", "valor_hora_historico": str(v_h)
                })
            salvar_seguro("lancamentos", pd.concat([df_lan, pd.DataFrame(novos)], ignore_index=True))

# === ABA 2: MEU DASHBOARD ===
with tabs[1]:
    meus = df_lan[df_lan["colaborador_email"] == user_email].copy()
    meus["horas"] = pd.to_numeric(meus["horas"], errors="coerce").fillna(0)
    
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Aprovado", f"{meus[meus['status_aprovaca']=='Aprovado']['horas'].sum():.1f}h")
    k2.metric("Pago", f"{meus[meus['status_aprovaca']=='Pago']['horas'].sum():.1f}h")
    k3.metric("Pendente", f"{meus[meus['status_aprovaca']=='Pendente']['horas'].sum():.1f}h")
    k4.metric("Rejeitado", f"{meus[meus['status_aprovaca']=='Rejeitado']['horas'].sum():.1f}h")
    
    st.dataframe(meus.sort_values("data_registro", ascending=False), use_container_width=True, hide_index=True)

# === ÁREA ADMIN ===
if user_email in ADMINS:
    with tabs[2]: # GERENCIAL
        t1, t2 = st.tabs(["Geral (Tabelona)", "Pagamentos"])
        with t1:
            with st.form("f_adm"):
                df_edt = st.data_editor(df_lan, num_rows="dynamic", use_container_width=True)
                if st.form_submit_button("Salvar Geral"): salvar_seguro("lancamentos", df_edt)
        with t2:
            mes = st.selectbox("Competência:", sorted(df_lan["competencia"].unique(), reverse=True))
            if st.button(f"Pagar Todos de {mes}"):
                df_lan.loc[(df_lan["competencia"]==mes) & (df_lan["status_aprovaca"]=="Aprovado"), "status_aprovaca"] = "Pago"
                salvar_seguro("lancamentos", df_lan)

    with tabs[3]: # BI FINANCEIRO
        df_bi = df_lan.copy()
        df_bi["horas"] = pd.to_numeric(df_bi["horas"], errors="coerce").fillna(0)
        df_bi["v_h"] = pd.to_numeric(df_bi["valor_hora_historico"], errors="coerce").fillna(0)
        df_bi["custo"] = df_bi["horas"] * df_bi["v_h"]
        val = df_bi[df_bi["status_aprovaca"].isin(["Aprovado", "Pago"])]
        
        m1, m2 = st.columns(2)
        m1.metric("Investimento Total", f"R$ {val['custo'].sum():,.2f}")
        m2.metric("Horas Totais", f"{val['horas'].sum():.1f}h")
        
        g1, g2 = st.columns(2)
        with g1: st.bar_chart(val.groupby("projeto")["custo"].sum())
        with g2: st.bar_chart(val.groupby("tipo")["horas"].sum())

    with tabs[4]: # CONFIG
        c1, c2 = st.tabs(["Usuários", "Projetos"])
        with c1:
            with st.form("fu"):
                du = st.data_editor(df_u_raw, num_rows="dynamic", use_container_width=True)
                if st.form_submit_button("Salvar Usuários"): salvar_seguro("config_usuarios", du)
        with c2:
            with st.form("fp"):
                dp = st.data_editor(df_p_raw, num_rows="dynamic", use_container_width=True)
                if st.form_submit_button("Salvar Projetos"): salvar_seguro("config_projetos", dp)