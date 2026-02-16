import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid
import time

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="OnCall System v20 - Phoenix", layout="wide", page_icon="🔥")

# === CONFIGURAÇÃO BLINDADA ===
# O sistema só vai procurar esta aba. Se não achar, ele cria.
ABA_PRINCIPAL = "banco_horas" 

# LISTA MESTRA DE COLUNAS (A Lei)
COLS_OFICIAIS = [
    "id", "data_registro", "colaborador_email", "projeto", "horas", 
    "status_aprovaca", "data_decisao", "competencia", "tipo", 
    "descricão", "email_enviado", "valor_hora_historico"
]

# --- 1. CONEXÃO ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 2. LEITURA INTELIGENTE ---
def carregar_dados():
    conn.clear() # Limpa o cache para não ler fantasma
    try:
        df = conn.read(worksheet=ABA_PRINCIPAL, ttl=0)
        
        # Se a planilha for virgem, retorna estrutura vazia
        if df.empty or len(df.columns) < 2:
            return pd.DataFrame(columns=COLS_OFICIAIS)
        
        # Normaliza
        df.columns = [str(c).strip().lower() for c in df.columns]
        
        # Se faltar coluna principal, recria estrutura
        if "projeto" not in df.columns:
            return pd.DataFrame(columns=COLS_OFICIAIS)

        # Garante que todas as colunas oficiais existam
        for col in COLS_OFICIAIS:
            if col not in df.columns:
                df[col] = ""
                
        return df[COLS_OFICIAIS] # Retorna limpo e ordenado
        
    except Exception:
        # Se der erro (ex: aba não existe ainda), retorna vazio para criar depois
        return pd.DataFrame(columns=COLS_OFICIAIS)

# Carrega os dados (Modo Leitura)
df_lan = carregar_dados()

# --- 3. CONFIGURAÇÕES (MANUAL PARA INÍCIO RÁPIDO) ---
# Usaremos listas manuais para o sistema rodar JÁ na planilha nova.
lista_projetos = [
    "Sustentação", "Projeto A", "Projeto B", "Consultoria", 
    "Infraestrutura", "Reunião Geral", "Outros"
]

# Usuários autorizados
dict_users = {
    "pedroivofernandesreis@gmail.com": {"valor": 100, "senha": "123"},
    "claudiele.andrade@gmail.com": {"valor": 150, "senha": "456"}
}
ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

# --- 4. FUNÇÃO SALVAR (APPEND SEGURO) ---
def salvar_novo_registro(dado_dict):
    try:
        conn.clear()
        
        # 1. Lê o estado atual
        df_atual = carregar_dados()
        
        # 2. Cria o novo registro
        df_novo = pd.DataFrame([dado_dict])
        
        # 3. Junta (Append)
        df_final = pd.concat([df_atual, df_novo], ignore_index=True)
        
        # 4. Limpa Nulos e Força Texto (Essencial para o Google)
        df_final = df_final.fillna("").astype(str)
        
        # 5. Grava
        conn.update(worksheet=ABA_PRINCIPAL, data=df_final)
        
        st.toast("✅ Registro Salvo!", icon="🚀")
        time.sleep(1); st.rerun()
        
    except Exception as e:
        st.error(f"❌ Erro ao salvar: {e}")

# Função para Atualizar Tabela Inteira (Admin)
def salvar_tabela_inteira(df_completo):
    try:
        conn.clear()
        df_final = df_completo.fillna("").astype(str)
        conn.update(worksheet=ABA_PRINCIPAL, data=df_final)
        st.success("✅ Tabela atualizada com sucesso!")
        time.sleep(1); st.rerun()
    except Exception as e:
        st.error(f"Erro: {e}")

# --- 5. LOGIN ---
st.sidebar.title("🔥 OnCall v20")
user_email = st.sidebar.selectbox("Usuário:", ["Selecione..."] + list(dict_users.keys()))

if user_email == "Selecione...":
    st.info("👈 Selecione seu usuário na lateral.")
    st.stop()

senha = st.sidebar.text_input("Senha:", type="password")
if senha != dict_users[user_email]["senha"]:
    st.error("Senha incorreta.")
    st.stop()

# --- 6. INTERFACE COMPLETA ---
# Recuperamos as abas bonitas!
tabs = st.tabs(["📝 Lançar", "📊 Meu Dash", "🛡️ Admin", "📈 BI"])

# === ABA 1: LANÇAR ===
with tabs[0]:
    st.markdown(f"### Olá, {user_email.split('@')[0]}!")
    with st.form("form_lancar"):
        c1, c2 = st.columns(2)
        proj = c1.selectbox("Projeto", lista_projetos)
        tipo = c2.selectbox("Tipo", ["Front-end","Back-end","Banco de Dados","Infra","Testes","Reunião","Outros"])
        data = c1.date_input("Data", datetime.now())
        horas = c2.number_input("Horas", min_value=0.5, step=0.5)
        desc = st.text_area("Descrição da Atividade")
        
        if st.form_submit_button("🚀 GRAVAR LANÇAMENTO"):
            novo = {
                "id": str(uuid.uuid4()), 
                "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "colaborador_email": user_email, 
                "projeto": proj, 
                "horas": str(horas),
                "status_aprovaca": "Pendente", 
                "data_decisao": "", 
                "competencia": data.strftime("%Y-%m"), 
                "tipo": tipo, 
                "descricão": desc, 
                "email_enviado": "", 
                "valor_hora_historico": str(dict_users[user_email]["valor"])
            }
            salvar_novo_registro(novo)

# === ABA 2: MEU DASHBOARD ===
with tabs[1]:
    if not df_lan.empty:
        meus = df_lan[df_lan["colaborador_email"] == user_email].copy()
        meus["horas"] = pd.to_numeric(meus["horas"], errors="coerce").fillna(0)
        
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Aprovado", f"{meus[meus['status_aprovaca']=='Aprovado']['horas'].sum():.1f}h")
        k2.metric("Pago", f"{meus[meus['status_aprovaca']=='Pago']['horas'].sum():.1f}h")
        k3.metric("Pendente", f"{meus[meus['status_aprovaca']=='Pendente']['horas'].sum():.1f}h")
        k4.metric("Rejeitado", f"{meus[meus['status_aprovaca']=='Rejeitado']['horas'].sum():.1f}h")
        
        st.dataframe(meus.sort_values("data_registro", ascending=False), use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum lançamento encontrado ainda.")

# === ABA 3: ADMINISTRAÇÃO ===
if user_email in ADMINS:
    with tabs[2]:
        st.markdown("### 🛡️ Painel de Controle")
        t1, t2 = st.tabs(["Edição Geral", "Pagamentos"])
        
        with t1:
            with st.form("form_admin"):
                df_editavel = st.data_editor(df_lan, num_rows="dynamic", use_container_width=True)
                if st.form_submit_button("💾 SALVAR ALTERAÇÕES GERAIS"):
                    salvar_tabela_inteira(df_editavel)
                    
        with t2:
            st.markdown("### Fechamento")
            if "competencia" in df_lan.columns and not df_lan.empty:
                mes = st.selectbox("Mês:", sorted(df_lan["competencia"].unique(), reverse=True))
                if st.button(f"💸 PAGAR TODOS DE {mes}"):
                    df_lan.loc[(df_lan["competencia"]==mes) & (df_lan["status_aprovaca"]=="Aprovado"), "status_aprovaca"] = "Pago"
                    salvar_tabela_inteira(df_lan)

# === ABA 4: BI FINANCEIRO ===
if user_email in ADMINS:
    with tabs[3]:
        st.markdown("### 📈 Inteligência Financeira")
        if not df_lan.empty:
            df_bi = df_lan.copy()
            df_bi["horas"] = pd.to_numeric(df_bi["horas"], errors="coerce").fillna(0)
            df_bi["v_h"] = pd.to_numeric(df_bi["valor_hora_historico"], errors="coerce").fillna(0)
            df_bi["custo"] = df_bi["horas"] * df_bi["v_h"]
            
            # Filtro de Validade
            val = df_bi[df_bi["status_aprovaca"].isin(["Aprovado", "Pago"])]
            
            c1, c2 = st.columns(2)
            c1.metric("Investimento Total", f"R$ {val['custo'].sum():,.2f}")
            c2.metric("Horas Totais", f"{val['horas'].sum():.1f}h")
            
            st.divider()
            g1, g2 = st.columns(2)
            with g1: 
                st.markdown("**Custo por Projeto**")
                st.bar_chart(val.groupby("projeto")["custo"].sum())
            with g2: 
                st.markdown("**Horas por Tipo**")
                st.bar_chart(val.groupby("tipo")["horas"].sum())
        else:
            st.warning("Comece a lançar dados para ver o BI.")

# === BOTÃO DE EMERGÊNCIA (SIDEBAR) ===
st.sidebar.divider()
st.sidebar.markdown("### 🛠️ Configuração Inicial")
if st.sidebar.button("🆘 CRIAR CABEÇALHOS"):
    conn.clear()
    df_reset = pd.DataFrame(columns=COLS_OFICIAIS)
    conn.update(worksheet=ABA_PRINCIPAL, data=df_reset)
    st.sidebar.success("Cabeçalhos criados! Dê F5.")